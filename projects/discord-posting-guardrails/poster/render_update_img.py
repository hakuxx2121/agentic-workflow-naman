import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
# ticker, AH, close, support, resistance, group, note
rows = [
 ("BMRN",55.66,55.66,55,None,"Working","Rptd Mon AMC · red wk −5.1%"),
 ("PLTR",172.60,175.40,172,None,"At level","Back on Jason's 172; 170–160 below · rptd Mon"),
 ("MRNA",227.50,228.44,200,227.81,"At level","Closed over 227.81, AH just under · ER Fri BMO"),
 ("GOOGL",278.39,280.03,None,280,"At level","Closed on 280, AH back under · under wk open"),
 ("IBM",250.04,250.04,230,250,"At level","Sitting on 250; under = 230 · red wk"),
 ("SOFI",16.58,16.77,15,16.76,"At level","Lost 16.76 AH; over = 19 try"),
 ("AKAM",85.96,86.53,83.24,85,"At level","Sub-85 buy area · ER Thu AMC"),
 ("MRVL",169.55,171.97,156,178,"Weak","Under 178 & 190 pivot · red wk −11.5%"),
 ("NBIS",150.50,151.64,None,157.50,"Weak","Under 157.50"),
 ("COIN",143.66,145.45,None,170,"Weak","Under 170, still green wk"),
 ("QQQ",681.62,685.28,None,699.50,"Weak","Under 699.50 SR flip · red wk −2.0%"),
 ("UBER",66.65,None,57.85,73,"In range","ER Wed BMO"),
 ("MCD",261.09,None,None,285,"In range","ER Wed BMO"),
 ("FSLY",21.01,None,19,22,"In range","ER Wed AMC"),
 ("TEM",76.91,None,75,83.41,"In range","Rptd Mon"),
 ("CRWV",52.81,None,50,64.61,"In range","−1.7% AH"),
 ("MU",849.60,None,800,980,"In range",""),
 ("AAPL",329.82,None,320,None,"In range","Rptd Mon AMC"),
 ("PFE",30.13,None,28.63,33,"In range","Rptd this AM"),
 ("HOOD",84.60,None,80.57,None,"In range",""),
 ("SPCX",138.84,None,130,148,"In range","−1.8% AH"),
 ("BA",173.30,None,None,182,"In range",""),
 ("RIVN",13.15,None,None,17,"In range",""),
]
C = {"Working":"#22c55e","At level":"#f59e0b","Weak":"#ef4444","In range":"#64748b"}
BG,CARD,TXT,SUB="#0f172a","#1e293b","#e2e8f0","#94a3b8"
plt.rcParams["font.family"]="DejaVu Sans"
rh=0.62; n=len(rows); groups=[]
for r in rows:
    if r[5] not in groups: groups.append(r[5])
H=2.2+n*rh+len(groups)*0.55+0.9
fig=plt.figure(figsize=(12,H),dpi=150); fig.patch.set_facecolor(BG)
ax=fig.add_axes([0,0,1,1]); ax.set_xlim(0,12); ax.set_ylim(H,0); ax.axis("off")
ax.text(0.4,0.6,"NDTL · Tue 11/3 · 8 PM after-hours",color=TXT,fontsize=20,weight="bold",va="center")
ax.text(0.4,1.15,"Jason's 11/2 plan levels · extended-hours prices · chart read, not financial advice",color=SUB,fontsize=10.5,va="center")
ax.add_patch(FancyBboxPatch((0.4,1.45),11.2,0.55,boxstyle="round,pad=0.02,rounding_size=0.12",fc="#334155",ec="none"))
ax.text(0.6,1.725,"Since 3:30:  broad AH dip 0.5–1.8% · PLTR testing 172 · SOFI lost 16.76 · MRNA closed over 227.81, AH just under",color=TXT,fontsize=10,va="center")
y=2.4
hdr=[(0.55,"TICKER"),(1.75,"AH"),(2.75,"AH %"),(3.7,"SUPPORT"),(4.75,"POSITION IN RANGE"),(7.35,"RESIST."),(8.35,"NOTE")]
for x,t in hdr: ax.text(x,y,t,color=SUB,fontsize=8.5,weight="bold",va="center")
y+=0.35
cur=None
for tk,px,cl,s,r,g,note in rows:
    if g!=cur:
        cur=g; y+=0.12
        ax.add_patch(Rectangle((0.4,y-0.12),0.08,0.3,color=C[g]))
        ax.text(0.6,y+0.03,g.upper(),color=C[g],fontsize=10,weight="bold",va="center"); y+=0.43
    ax.add_patch(FancyBboxPatch((0.4,y-rh/2+0.04),11.2,rh-0.08,boxstyle="round,pad=0,rounding_size=0.08",fc=CARD,ec="none"))
    ax.add_patch(Rectangle((0.4,y-rh/2+0.04),0.06,rh-0.08,color=C[g]))
    ax.text(0.6,y,tk,color=TXT,fontsize=11.5,weight="bold",va="center")
    ax.text(1.75,y,f"{px:,.2f}",color=TXT,fontsize=11,va="center")
    if cl:
        ch=(px/cl-1)*100; col="#22c55e" if ch>0.05 else "#ef4444" if ch<-0.05 else SUB
        ax.text(2.75,y,f"{ch:+.1f}%".replace("-","−"),color=col,fontsize=10,va="center")
    else: ax.text(2.75,y,"–",color=SUB,fontsize=10,va="center")
    ax.text(3.7,y,f"{s:g}" if s else "–",color="#f87171" if s else SUB,fontsize=10.5,va="center")
    ax.text(7.35,y,f"{r:g}" if r else "–",color="#4ade80" if r else SUB,fontsize=10.5,va="center")
    # range bar
    x0,x1=4.75,7.1
    ax.add_patch(FancyBboxPatch((x0,y-0.05),x1-x0,0.1,boxstyle="round,pad=0,rounding_size=0.05",fc="#475569",ec="none"))
    if s and r:
        lo,hi=min(s,r),max(s,r); f=(px-lo)/(hi-lo) if hi>lo else 0.5; f=max(-0.04,min(1.04,f))
    elif s: f=0.08 if px<=s*1.02 else 0.3
    elif r: f=0.92 if px>=r*0.98 else 0.7
    else: f=0.5
    f=max(0,min(1,f))
    ax.plot([x0+f*(x1-x0)],[y],"o",ms=9,color=C[g],mec="white",mew=1.2)
    ax.text(8.35,y,note,color=SUB,fontsize=9.5,va="center")
    y+=rh
y+=0.25
ax.text(0.4,y,"No levels from Jason:  META 618.15 · AMAT 376.48 · NCLH 17.35 · SPY 752.22 · DIA 515.40 · IWM 278.64",color=SUB,fontsize=9.5,va="center")
fig.savefig("update_preview.png",facecolor=BG)
print("ok")
