"""A restrained original demo bed, track fitting, and voice-priority music mixing."""
from array import array
import math
from .sound_render import RATE, mix_voice, smooth


def ambient_bed(rate=RATE):
    """Original slow harmonic texture: no percussion, lead melody or vocals."""
    chords=[(146.832,174.614,220.0),(116.541,146.832,174.614),
            (130.813,174.614,220.0),(130.813,146.832,195.998)]
    output=array('f',[0.0])*(32*rate*2)
    for frame in range(32*rate):
        t=frame/rate;section=int(t//8);blend=smooth(min(1,(t%8)/2.5))
        for c in (0,1):
            value=0
            for index,weight in (((section-1)%4,1-blend),(section,blend)):
                for voice,freq in enumerate(chords[index]):
                    phase=2*math.pi*(freq*(1+(c*2-1)*.0007))*t+voice*.4
                    value+=weight*(math.sin(phase)+.10*math.sin(phase*2))*.055
            output[frame*2+c]=value*(.94+.06*math.sin(2*math.pi*t/13+c*.2))
    return output


def pulse_bed(rate=RATE):
    """Original restrained 96 BPM low percussion over the existing harmonic bed."""
    output=ambient_bed(rate)
    for frame in range(len(output)//2):
        t=frame/rate;beat=t%(60/96);offbeat=(t+30/96)%(60/96)
        pulse=.14*math.sin(2*math.pi*(70*beat+12*(1-math.exp(-20*beat))))*math.exp(-14*beat)
        tick=.018*math.sin(2*math.pi*620*offbeat)*math.exp(-90*offbeat)
        for channel in (0,1):output[2*frame+channel]=output[2*frame+channel]*.55+pulse+tick
    return output


def fit_track(samples, duration, loop=True, crossfade_sec=1, rate=RATE):
    if len(samples)%2 or len(samples)//2<round(.25*rate):raise ValueError('Music needs at least 0.25 seconds of stereo audio.')
    frames=round(duration*rate)
    if not frames>0:raise ValueError('Music duration must be positive.')
    active=min(frames,len(samples)//2)
    output=array('f',samples[:frames*2])
    if loop:
        clip_frames=len(samples)//2;overlap=min(round(crossfade_sec*rate),clip_frames//4)
        while len(output)//2<frames:
            base=len(output)//2-overlap
            for i in range(overlap):
                weight=smooth(i/max(1,overlap-1))
                for c in (0,1):output[2*(base+i)+c]=output[2*(base+i)+c]*(1-weight)+samples[2*i+c]*weight
            output.extend(samples[overlap*2:])
        output=output[:frames*2];active=frames
    else:output.extend(array('f',[0.0])*max(0,frames*2-len(output)))
    rms=math.sqrt(sum(v*v for v in output[:active*2])/max(1,active*2))
    if rms<1e-6:raise ValueError('Selected music is silent.')
    peak=max(abs(v) for v in output)
    gain=min(.1/rms,.5/max(peak,1e-12))  # -20dBFS reference, with >=6dB peak headroom.
    output=array('f',(v*gain for v in output))
    return output,dict(active_duration=active/rate,normalization_gain_db=20*math.log10(gain),
                       prepared_rms_dbfs=20*math.log10(max(rms*gain,1e-12)))


def mix_music(effects, narration, music, settings, active_duration, rate=RATE):
    duration=len(effects)/(rate*2)
    if len(effects)%2 or len(music)!=len(effects):raise ValueError('Music/effects stems must match video duration.')
    if narration is not None and len(narration)>len(effects):raise ValueError('Narration exceeds the video; retime it first.')
    end=min(duration,settings.end_sec if settings.end_sec is not None else duration,settings.start_sec+active_duration)
    if settings.enabled and settings.start_sec>=end:raise ValueError('Music start must fall inside the video.')
    voice_gain=10**(settings.narration_gain_db/20);effects_gain=10**(settings.effects_gain_db/20)
    voice=array('f',(v*voice_gain for v in narration)) if narration is not None else None
    fx=array('f',(v*effects_gain for v in effects))
    base,base_stats=mix_voice(fx,voice,rate)
    bed=array('f',[0.0])*len(base);duck=1.0;window=max(1,round(.02*rate))
    voice_blocks=effect_blocks=0;minimum_duck=1.0;gain=10**(settings.music_gain_db/20)
    voice_limit=10**(settings.voice_threshold_dbfs/20);effect_limit=10**(settings.effects_threshold_dbfs/20)
    offset=round(settings.start_sec*rate)
    def energy(values):return math.sqrt(sum(v*v for v in values)/max(1,len(values)))
    for frame in range(0,len(base)//2,window):
        stop=min(len(base)//2,frame+window)
        vrms=energy(voice[frame*2:min(stop*2,len(voice))]) if voice else 0
        frms=energy(fx[frame*2:stop*2]);target=1.0
        if vrms>voice_limit:
            voice_blocks+=1;target=min(target,10**(settings.voice_duck_db/20))
            first=max(0,frame-offset);last=max(0,stop-offset);mrms=energy(music[first*2:last*2])
            if mrms*gain>1e-12:target=min(target,vrms*10**(-settings.voice_margin_db/20)/(mrms*gain))
        if frms>effect_limit:effect_blocks+=1;target=min(target,10**(settings.effects_duck_db/20))
        coefficient=math.exp(-1/(rate*(settings.attack_sec if target<duck else settings.release_sec)))
        for i in range(frame,stop):
            duck=target+(duck-target)*coefficient;minimum_duck=min(minimum_duck,duck)
            t=i/rate
            if not settings.enabled or i<offset or t>=end:continue
            envelope=smooth((t-settings.start_sec)/max(.005,settings.fade_in_sec))*smooth((end-t)/max(.005,settings.fade_out_sec))
            for c in (0,1):bed[2*i+c]=music[2*(i-offset)+c]*gain*duck*envelope
    combined=array('f',(a+b for a,b in zip(base,bed)))
    peak=max((abs(v) for v in combined),default=0);scale=min(1,.891/max(peak,1e-12))
    if scale<1:combined=array('f',(v*scale for v in combined))
    stats=dict(base=base_stats,music_rms_dbfs=20*math.log10(max(energy(bed),1e-12)),
               final_peak_dbfs=20*math.log10(max(peak*scale,1e-12)),headroom_scale=scale,
               voice_duck_blocks=voice_blocks,effects_duck_blocks=effect_blocks,
               minimum_music_duck_db=20*math.log10(max(minimum_duck,1e-12)))
    return combined,bed,stats
