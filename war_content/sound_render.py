"""Deterministic original Foley, WAV replacement, and voice-priority mixing."""
from array import array
import math
import random
import sys
import wave

RATE = 48000


def smooth(value):
    t=max(0.0,min(1.0,value))
    return t*t*(3-2*t)


def read_wave(path, rate=RATE):
    try:
        with wave.open(str(path),'rb') as audio:
            channels, width, source_rate = audio.getnchannels(), audio.getsampwidth(), audio.getframerate()
            if width != 2 or channels not in (1,2) or not 8000 <= source_rate <= 96000 or audio.getnframes()/source_rate > 151:
                raise ValueError('WAV must be 16-bit PCM, mono/stereo, 8–96kHz and at most 151 seconds.')
            pcm=array('h',audio.readframes(audio.getnframes()))
    except (wave.Error,EOFError):
        raise ValueError('Cannot read WAV: provide an uncompressed 16-bit PCM file.') from None
    if sys.byteorder != 'little': pcm.byteswap()
    frames=len(pcm)//channels
    if not frames: raise ValueError('WAV sample is empty.')
    result=array('f',[0.0])*(max(1,round(frames*rate/source_rate))*2)
    for i in range(len(result)//2):
        position=min(frames-1,i*source_rate/rate);a=int(position);b=min(frames-1,a+1);fraction=position-a
        for channel in (0,1):
            c=min(channel,channels-1)
            result[2*i+channel]=(pcm[a*channels+c]*(1-fraction)+pcm[b*channels+c]*fraction)/32768
    return result


def write_wave(path, samples, rate=RATE):
    if len(samples)%2 or any(not math.isfinite(s) for s in samples):
        raise ValueError('Sound output must be finite stereo samples.')
    pcm=array('h',(max(-32767,min(32767,round(s*32767))) for s in samples))
    if sys.byteorder != 'little': pcm.byteswap()
    with wave.open(str(path),'wb') as target:
        target.setnchannels(2);target.setsampwidth(2);target.setframerate(rate);target.writeframes(pcm.tobytes())


def synth_sample(effect, rate=RATE):
    """Original non-recorded material. No downloaded media or licensing dependency."""
    rng=random.Random('atlas-foley-v1:'+effect)
    duration={'footsteps':4/2.2,'heavy_steps':4/1.5,'hooves':2.4,'tracks':2,'wheels':2,
              'cannon':2,'musket':.9,'rifle':.9,'clash':.6}[effect]
    output=array('f',[0.0])*round(duration*rate)
    if effect in ('tracks','wheels'):
        low=0.0
        for i in range(len(output)):
            t=i/rate;noise=rng.uniform(-1,1);low+=.035*(noise-low)
            if effect=='tracks':
                engine=.29*math.sin(2*math.pi*53*t)+.14*math.sin(2*math.pi*106*t)+.07*math.sin(2*math.pi*159*t)
                chatter=(.5+.5*math.sin(2*math.pi*9*t))**6
                output[i]=engine+.32*low+.10*(noise-low)*chatter+.07*chatter*math.sin(2*math.pi*647*t)
            else:
                output[i]=.45*low+.12*math.sin(2*math.pi*43*t)+.06*(noise-low)*(.5+.5*math.sin(2*math.pi*5*t))**8
    else:
        if effect=='footsteps':beats=[i/2.2 for i in range(4)]
        elif effect=='heavy_steps':beats=[i/1.5 for i in range(4)]
        elif effect=='hooves':beats=[cycle+offset for cycle in (0,.6,1.2,1.8) for offset in (0,.12,.31,.42)]
        else:beats=[0]
        for beat in beats:
            length={'footsteps':.15,'heavy_steps':.28,'hooves':.11,'cannon':2,'musket':.9,'rifle':.9,'clash':.6}[effect]
            start=round(beat*rate);variation=rng.uniform(.85,1.0);low=0.0
            for j in range(min(round(length*rate),len(output)-start)):
                t=j/rate;noise=rng.uniform(-1,1);low+=.12*(noise-low)
                if effect in ('footsteps','heavy_steps','hooves'):
                    freq={'footsteps':130,'heavy_steps':62,'hooves':310}[effect]
                    decay={'footsteps':32,'heavy_steps':17,'hooves':65}[effect]
                    value=(.43*math.sin(2*math.pi*freq*t)*math.exp(-decay*t)+.37*low*math.exp(-decay*.6*t)+.20*noise*math.exp(-90*t))
                    if effect=='heavy_steps':
                        # Keep the weight audible on phone speakers as well as
                        # bass-capable headphones: surface crunch + low-mid body.
                        value+=.28*(noise-low)*math.exp(-25*t)+.18*math.sin(2*math.pi*186*t)*math.exp(-20*t)
                    value*=smooth(t/.0015)*variation
                elif effect=='clash':
                    value=(.32*math.sin(2*math.pi*1513*t)+.22*math.sin(2*math.pi*2377*t))*math.exp(-10*t)+.45*noise*math.exp(-60*t)
                else:
                    # Explicit firing cues only: transient + body + diffuse tail.
                    heavy=effect=='cannon';value=.65*noise*math.exp(-(24 if heavy else 95)*t)
                    value+=.42*math.sin(2*math.pi*(48 if heavy else 105)*t)*math.exp(-(4 if heavy else 18)*t)
                    value+=.28*low*math.exp(-(2.5 if heavy else 8)*t)
                output[start+j]+=value
    # Taper loop seams and one-shot tails to prevent clicks.
    for i in range(min(round(rate*.008),len(output)//2)):
        gain=smooth(i/(rate*.008));output[i]*=gain;output[-1-i]*=gain
    return output


def render_effects(plan, samples=None, rate=RATE):
    if plan.unresolved_units:
        raise ValueError('Choose sound profiles for: '+', '.join(plan.unresolved_units))
    output=array('f',[0.0])*(round(plan.duration*rate)*2)
    samples=samples or {};cache={}
    for cue in plan.cues:
        if cue.effect not in cache:
            if cue.effect in samples:
                stereo=read_wave(samples[cue.effect],rate)
                cache[cue.effect]=array('f',((stereo[i]+stereo[i+1])*.5 for i in range(0,len(stereo),2)))
            else:cache[cue.effect]=synth_sample(cue.effect,rate)
        clip=cache[cue.effect];length=round((cue.end-cue.start)*rate);start=round(cue.start*rate)
        # Different stable offsets keep continuous layers from phasing identically.
        offset=cue.seed%len(clip) if cue.loop else 0
        gain=10**(cue.gain_db/20)
        for j in range(min(length,len(output)//2-start)):
            if not cue.loop and j>=len(clip):break
            t=j/rate;remaining=(length-j)/rate
            envelope=smooth(t/.4)*smooth(remaining/.4) if cue.loop else smooth(t/.001)*smooth(remaining/.03)
            pan=cue.pan_start+(cue.pan_end-cue.pan_start)*j/max(1,length-1)
            value=clip[(j+offset)%len(clip)]*gain*envelope
            output[2*(start+j)]+=value*math.sqrt((1-pan)/2)
            output[2*(start+j)+1]+=value*math.sqrt((1+pan)/2)
    return output


def mix_voice(effects, narration=None, rate=RATE):
    if narration is not None and len(narration)>len(effects):
        raise ValueError('Narration exceeds video duration; retime the video before mixing.')
    output=array('f',effects);duck=1.0;window=max(1,round(.02*rate));voice=narration or array('f')
    speech_blocks=0
    for frame in range(0,len(output)//2,window):
        stop=min(len(output)//2,frame+window)
        values=voice[frame*2:min(stop*2,len(voice))]
        active=bool(values) and math.sqrt(sum(v*v for v in values)/len(values))>.008
        target=.25 if active else 1.0
        if active:speech_blocks+=1
        coefficient=math.exp(-1/(rate*(.02 if target<duck else .22)))
        for i in range(frame,stop):
            duck=target+(duck-target)*coefficient
            for channel in (0,1):
                index=2*i+channel;output[index]=output[index]*duck+(voice[index] if index<len(voice) else 0)
    peak=max((abs(v) for v in output),default=0);scale=min(1,.891/max(peak,1e-12))
    if scale<1:output=array('f',(v*scale for v in output))
    rms=math.sqrt(sum(v*v for v in output)/max(1,len(output)))
    return output,dict(peak_dbfs=20*math.log10(max(peak*scale,1e-12)),rms_dbfs=20*math.log10(max(rms,1e-12)),
                       headroom_scale=scale,speech_blocks=speech_blocks,sample_rate=rate)
