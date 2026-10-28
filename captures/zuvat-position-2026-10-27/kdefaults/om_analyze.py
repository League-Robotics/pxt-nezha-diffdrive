import csv, glob, math, statistics as st
MM=0.079322; TW=111.6
print("file | heading deg (cmd 90) | move ms | wheel speed mm/s median/peak (enc) | body rate deg/s median | stall frames mid-move | i2cf")
out=[]
for p in sorted(glob.glob("om*_*.csv")):
    f=[{k:float(v) for k,v in r.items()} for r in csv.DictReader(open(p))]
    dth=math.degrees(((f[-1]['posr']-f[0]['posr'])-(f[-1]['posl']-f[0]['posl']))*MM/TW)
    idx=[i for i in range(1,len(f)) if f[i]['posl']!=f[i-1]['posl'] or f[i]['posr']!=f[i-1]['posr']]
    a,b=idx[0],idx[-1]; ms=f[b]['t_ms']-f[a-1]['t_ms']
    sp=[];rate=[];stall=0
    for i in range(a,b+1):
        dt=(f[i]['t_ms']-f[i-1]['t_ms'])/1000
        dl=(f[i]['posl']-f[i-1]['posl'])*MM/dt; dr=(f[i]['posr']-f[i-1]['posr'])*MM/dt
        sp.append(max(abs(dl),abs(dr))); rate.append(math.degrees((dr-dl)/TW))
        mid=a+(b-a)*0.2<=i<=b-(b-a)*0.2
        if mid and f[i]['posl']==f[i-1]['posl'] and f[i]['posr']==f[i-1]['posr']: stall+=1
    mid=sp[len(sp)//5:-len(sp)//5 or None]; mr=rate[len(rate)//5:-len(rate)//5 or None]
    print(f"{p[:-4]} | {abs(dth):.1f} | {ms:.0f} | {st.median(mid):.0f}/{max(sp):.0f} | {st.median([abs(x) for x in mr]):.0f} | {stall} | {f[-1]['i2cf']-f[0]['i2cf']:.0f}")
