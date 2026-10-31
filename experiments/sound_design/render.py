"""Bounded DSP interpreter: no code evaluation, file access or network access."""
from array import array
import math
import random
from .models import Recipe

RATE=48000


def render(recipe: Recipe,rate=RATE):
    if not 8000<=rate<=48000:raise ValueError('Experimental render rate must be 8–48kHz.')
    # Revalidate even caller-created or edited instances before allocating buffers.
    recipe=Recipe.model_validate(recipe.model_dump())
    output=array('f',[0.0])*(round(recipe.duration*rate)*2)
    for number,layer in enumerate(recipe.layers):
        rng=random.Random(recipe.seed+number*100003)
        starts=[layer.start]
        if layer.repeat_every:
            starts=[];event=0
            while layer.start+event*layer.repeat_every<recipe.duration:
                offset=rng.uniform(-layer.jitter,layer.jitter)*layer.repeat_every if event else 0
                starts.append(max(layer.start,layer.start+event*layer.repeat_every+offset));event+=1
        pan_l=math.sqrt((1-layer.pan)/2);pan_r=math.sqrt((1+layer.pan)/2)
        gain=10**(layer.gain_db/20)
        # Bounded one-pole high/low-pass sections. Reset each hit's filter state.
        hp=math.exp(-2*math.pi*layer.highpass/rate);lp=1-math.exp(-2*math.pi*min(layer.lowpass,rate*.45)/rate)
        for start in starts:
            begin=round(start*rate);length=min(round(layer.duration*rate),len(output)//2-begin)
            phase=rng.random() if layer.repeat_every else 0;prev=high=low=0.0
            hit_gain=rng.uniform(.88,1.0) if layer.repeat_every else 1.0
            for j in range(max(0,length)):
                t=j/rate;frequency=min(rate*.45,layer.frequency_start+(layer.frequency_end-layer.frequency_start)*t/layer.duration)
                phase=(phase+frequency/rate)%1
                value=rng.uniform(-1,1) if layer.source=='noise' else math.sin(2*math.pi*phase) if layer.source=='sine' else 1-4*abs(phase-.5)
                high=hp*(high+value-prev);prev=value;low+=lp*(high-low)
                attack=min(1,t/layer.attack);release=min(1,(layer.duration-t)/layer.release)
                envelope=attack*attack*(3-2*attack)*release*release*(3-2*release)*math.exp(-layer.decay*t)
                modulation=1-layer.tremolo_depth*(.5+.5*math.sin(2*math.pi*layer.tremolo_hz*t)) if layer.tremolo_hz else 1
                sample=low*gain*hit_gain*envelope*modulation
                index=2*(begin+j);output[index]+=sample*pan_l;output[index+1]+=sample*pan_r
    # Prevent edge clicks. High-pass sections suppress DC while preserving exact
    # silence outside events. Loop candidates have a short boundary dip,
    # not a claim of phase-perfect loop synthesis.
    edge=max(1,round(.005*rate))
    for frame in range(len(output)//2):
        fade=min(1,frame/edge,(len(output)//2-1-frame)/edge)
        for c in (0,1):output[frame*2+c]*=fade
    peak=max(abs(v) for v in output)
    scale=min(1,.891/max(peak,1e-12))
    if scale<1:output=array('f',(v*scale for v in output))
    return output,measure(output,rate,scale)


def measure(samples,rate=RATE,scale=1):
    if not samples or len(samples)%2 or any(not math.isfinite(v) for v in samples):
        raise ValueError('Expected finite, nonempty stereo samples.')
    rms=math.sqrt(sum(v*v for v in samples)/len(samples));peak=max(abs(v) for v in samples)
    # Phone-band energy proxy: high-pass at 180Hz, not a listening-quality score.
    coefficient=math.exp(-2*math.pi*180/rate);prev=high=energy=0
    for i in range(0,len(samples),2):
        value=(samples[i]+samples[i+1])*.5;high=coefficient*(high+value-prev);prev=value;energy+=high*high
    phone=math.sqrt(energy/(len(samples)//2))
    metrics=dict(peak_dbfs=20*math.log10(max(peak,1e-12)),rms_dbfs=20*math.log10(max(rms,1e-12)),
                 phone_band_rms_dbfs=20*math.log10(max(phone,1e-12)),headroom_scale=scale,
                 duration=len(samples)/(2*rate),boundary_step=max(abs(samples[0]-samples[-2]),abs(samples[1]-samples[-1])))
    metrics['dc_offset']=max(abs(sum(samples[c::2])/max(1,len(samples)//2)) for c in (0,1))
    issues=[]
    if rms<.003:issues.append('Output is too quiet or silent; strengthen audible layers.')
    if phone<.0015:issues.append('Very little phone-band energy; add appropriate surface texture or midrange body.')
    if scale<.4:issues.append('Layers overload the bus; lower layer gains instead of relying on master attenuation.')
    if metrics['dc_offset']>.02:issues.append('Output has excessive DC offset; use balanced filtered layers.')
    metrics['issues']=issues;metrics['technical_pass']=not issues
    return metrics
