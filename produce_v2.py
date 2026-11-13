import math, random, time, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy.io import wavfile

OUT=Path('/mnt/data')
AS=OUT/'eazyfix_ad_assets'
AS.mkdir(exist_ok=True)
W,H=720,1280
FPS=30
DURATION=23.6
N=int(FPS*DURATION)
COL={'bg':'#080B17','bg2':'#0D1228','navy':'#151B34','white':'#F6F7FF','muted':'#A2ABCA','lav':'#D9D6FF','purple':'#6856FF','purple2':'#9074FF','cyan':'#31D2F7','lime':'#C5FA72','red':'#FF6B83','outline':'#333F63','black':'#080D1D'}
FONT_DIR='/usr/share/fonts/opentype/inter'
font_files={'black':'Inter-ExtraBold.otf','bold':'Inter-Bold.otf','med':'Inter-Medium.otf','reg':'Inter-Regular.otf'}
FONT={}
def ft(sz,kind='bold'):
 key=(sz,kind)
 if key not in FONT:FONT[key]=ImageFont.truetype(f'{FONT_DIR}/{font_files[kind]}',int(sz))
 return FONT[key]
def rgba(c,a=255):
 c=COL.get(c,c)
 if isinstance(c,tuple):return (*c[:3],int(a))
 c=c.lstrip('#');return tuple(int(c[i:i+2],16) for i in (0,2,4))+(int(a),)
def clamp(x,a=0,b=1):return max(a,min(b,x))
def ease(x):
 x=clamp(x);return 1-(1-x)**3
def ein(x):x=clamp(x);return x*x*x
def eio(x):
 x=clamp(x);return x*x*(3-2*x)
def spring(x):
 x=clamp(x);return 1+(2.1**(-10*x))*math.sin((x-.11)*math.pi*3.5)*.55 if x<1 else 1

def measure(s,size,kind='bold'):
 bb=ft(size,kind).getbbox(s);return bb[2]-bb[0]
def fit(s,maxwidth,sz=74,kind='black'):
 while sz>20 and measure(s,sz,kind)>maxwidth:sz-=1
 return sz

def txt(im,x,y,s,size=50,color='white',kind='bold',alpha=255,anchor='lt',spacing=0):
 if alpha<=0 or not s:return
 d=ImageDraw.Draw(im)
 color=rgba(color,alpha)
 d.text((int(x),int(y)),s,font=ft(size,kind),fill=color,anchor=anchor,spacing=spacing,stroke_width=0)

def rr(im,xy,r,fill,outline=None,width=1):
 d=ImageDraw.Draw(im)
 d.rounded_rectangle(tuple(map(int,xy)),radius=int(r),fill=fill if isinstance(fill,tuple) else rgba(fill),outline=outline if isinstance(outline,tuple) or not outline else rgba(outline),width=width)

def line(im,xy,fill='white',width=1):ImageDraw.Draw(im).line(xy,fill=rgba(fill) if isinstance(fill,str) else fill,width=int(width),joint='curve')
def circle(im,cx,cy,r,fill,outline=None,width=1):ImageDraw.Draw(im).ellipse((int(cx-r),int(cy-r),int(cx+r),int(cy+r)),fill=rgba(fill) if isinstance(fill,str) else fill,outline=rgba(outline) if isinstance(outline,str) else outline,width=width)

def gradient_color_panel(w,h,c1,c2,rad=(.72,.20),blur=.45):
 ys,xs=np.mgrid[0:h,0:w].astype(np.float32)
 xs/=w;ys/=h
 p=np.maximum(0,1-((xs-rad[0])**2+(ys-rad[1])**2)/(.56**2))**1.5
 a=np.array(rgba(c1)[:3]);b=np.array(rgba(c2)[:3]);z=np.clip(a[None,None,:]+(b-a)[None,None,:]*p[:,:,None],0,255).astype('uint8')
 return Image.fromarray(z,'RGB').convert('RGBA')

# Pre-computed smooth dark base; alpha composited moving gradient blooms on every frame
basearr=np.zeros((H,W,3),dtype=np.uint8)
for y in range(H):
 fac=y/H
 basearr[y,:,:]=np.array([8+int(2*fac),11+int(5*fac),23+int(15*fac)])
BASE=Image.fromarray(basearr,'RGB').convert('RGBA')
# Blur once for each soft colored glow, and translate them for movement
GLOWS=[]
for r,col in [(295,rgba('purple',48)),(270,rgba('cyan',24)),(220,rgba('purple2',24))]:
 g=Image.new('RGBA',(2*r+2,2*r+2));d=ImageDraw.Draw(g)
 d.ellipse((r//2,r//2,3*r//2,3*r//2),fill=col)
 GLOWS.append(g.filter(ImageFilter.GaussianBlur(int(r*.27))))

def background(t,scene=0):
 im=BASE.copy()
 spots=[(430+180*math.sin(t*.34),285+100*math.cos(t*.52)),(35+130*math.cos(t*.5),890+250*math.sin(t*.19)),(670+100*math.cos(t*.32),1060+110*math.sin(t*.48))]
 for (x,y),g in zip(spots,GLOWS):
  im.alpha_composite(g,(int(x-g.width/2),int(y-g.height/2))) if 0<=x-g.width/2 and 0<=y-g.height/2 and x+g.width/2<=W and y+g.height/2<=H else im.paste_composite(g,int(x-g.width/2),int(y-g.height/2)) if False else composite_outside(im,g,int(x-g.width/2),int(y-g.height/2))
 d=ImageDraw.Draw(im)
 # fine receding design grid, continuously scrolling
 gy=int((t*19)%72)
 for x in range(-30,W+50,72):d.line((x,0,x,H),fill=(151,164,247,12),width=1)
 for y in range(-70,H+70,72):d.line((0,y+gy,W,y+gy),fill=(151,164,247,12),width=1)
 # micro sparks + diagonal scan line
 for j in range(22):
  xx=(j*199+int(t*(12+j%3*3)))%W;yy=(j*331+int(t*(17+j%4*3)))%H
  d.ellipse((xx,yy,xx+2,yy+2),fill=(195,213,255,35))
 if t<20:
  y=int((t*110)%H);d.line((0,y,W,y),fill=(130,120,255,20),width=2)
 return im

def composite_outside(im,layer,x,y):
 # copy overlay clipped to image bounds
 x2=max(0,x);y2=max(0,y);xe=min(W,x+layer.width);ye=min(H,y+layer.height)
 if xe>x2 and ye>y2:im.alpha_composite(layer.crop((x2-x,y2-y,xe-x,ye-y)),(x2,y2))

def topbar(im,t,chapter='MADE FOR YOUR BUSINESS'):
 d=ImageDraw.Draw(im)
 circle(im,53,88,5,'cyan')
 txt(im,69,78,'EAZYFIX',22,'white','black')
 txt(im,681,79,'•  DIGITAL STUDIO',15,'muted','med',anchor='rt')
 line(im,[(42,119),(680,119)],(125,144,204,61),1)
 txt(im,42,1223,chapter,16,'muted','med')
 # timeline bottom
 rr(im,(42,1254,678,1257),2,(115,122,165,77))
 rr(im,(42,1254,42+636*clamp(t/DURATION),1257),2,'cyan')

def particles(im,t,seed=0,amount=20,origin=(360,650),amp=320):
 d=ImageDraw.Draw(im)
 r=random.Random(seed)
 for i in range(amount):
  a=r.random()*2*math.pi
  v=100+r.random()*amp
  tt=t+.2*r.random()
  x=origin[0]+math.cos(a)*v*tt;y=origin[1]+math.sin(a)*v*tt
  if 0<=x<W and 0<=y<H:
   radius=2 if i%3 else 4
   d.ellipse((x-radius,y-radius,x+radius,y+radius),fill=rgba(['cyan','purple2','white'][i%3],int(190*max(0,1-tt/1.4))))

def framewindow(name='ATELIER',typ='shop',w=626,h=648):
 # Entire website reconstructed as sharp vector UI, not a video slideshow
 im=Image.new('RGBA',(w,h),(0,0,0,0))
 rr(im,(1,1,w-2,h-2),28,'#F8FAFE',outline='#8B93B7',width=2)
 rr(im,(1,1,w-2,64),28,'#E9ECF6');ImageDraw.Draw(im).rectangle((1,38,w-1,64),fill=rgba('#E9ECF6'))
 for i,c in enumerate(('#FF6D7C','#FFC453','#57D5AA')):circle(im,26+i*24,33,6,c)
 rr(im,(118,17,w-34,49),15,'white')
 txt(im,139,22,'eazyfix demo / '+name.lower(),15,'#7884A4','med')
 if typ=='shop':
  rr(im,(2,65,w-2,h-2),0,'#F6F3EC')
  txt(im,31,88,'ATELIER',27,'#1B2337','black')
  txt(im,w-33,97,'SHOP   STORY   MENU',14,'#3F4B61','bold',anchor='rt')
  txt(im,32,178,'Objects with',45,'#22263B','black')
  txt(im,32,235,'character.',55,'#22263B','black')
  txt(im,33,331,'Σύγχρονο ηλεκτρονικό κατάστημα',17,'#74717A','med')
  rr(im,(32,381,272,432),22,'#242836');txt(im,53,396,'DISCOVER NOW',17,'white','black')
  # premium furniture silhouettes
  circle(im,472,350,121,'#EED6BB')
  rr(im,(429,265,514,445),36,'#AC7B53');rr(im,(394,360,550,443),25,'#C58D60')
  line(im,[(421,437),(401,505)],(101,74,57,255),5);line(im,[(529,437),(552,508)],(101,74,57,255),5)
  for j in range(3):
   xx=32+j*190
   rr(im,(xx,528,xx+176,616),15,['#D8E3F0','#F2DDCF','#E0E1CE'][j])
   circle(im,xx+89,571,29,['#7188A2','#AF7968','#778575'][j])
 elif typ=='food':
  rr(im,(2,65,w-2,h-2),0,'#FFF5E8')
  txt(im,33,91,'TERRA',27,'#42291C','black')
  txt(im,33,175,'Fresh. Local.',51,'#3B261D','black')
  txt(im,33,237,'Delicious.',59,'#CB673E','black')
  txt(im,35,325,'Το δικό σου digital μενού',21,'#785D4F','med')
  rr(im,(34,392,240,449),23,'#B44C2F');txt(im,61,408,'ΔΕΣ ΤΟ ΜΕΝΟΥ',18,'white','black')
  for j,(x,y,r) in enumerate([(482,323,111),(365,534,76),(533,544,71)]):
   circle(im,x,y,r,'#F3D1A5');circle(im,x,y,r-12,'#FFFFFF')
   for k in range(11):
    a=k*2*math.pi/11
    xx=x+(r-42)*math.cos(a);yy=y+(r-42)*math.sin(a)
    circle(im,xx,yy,9,('#A7C769' if k%3==0 else '#DF7D58'))
   circle(im,x,y,r/3,'#E5A048')
 elif typ=='estate':
  rr(im,(2,65,w-2,h-2),0,'#EDF4FB')
  rr(im,(2,65,w-2,358),0,'#163858')
  txt(im,31,94,'SAMOTHRAKI REAL ESTATE',20,'white','black')
  txt(im,31,169,'Βρες τον δικό σου',40,'white','black')
  txt(im,31,229,'χώρο.',63,'#B8E6FC','black')
  rr(im,(30,313,w-30,368),15,'white')
  txt(im,48,328,'Σαλαμίνα     |     Ακίνητα                 ⌕',21,'#667994','med')
  for j in range(3):
   x=26+j*201
   rr(im,(x,397,x+183,557),14,['#E2E1DA','#D5D7E1','#C9DFDC'][j])
   # vector architecture
   ImageDraw.Draw(im).polygon([(x+17,474),(x+87,416),(x+170,474)],fill=rgba(['#728FA8','#A8867B','#587A77'][j]))
   rr(im,(x+39,475,x+142,559),2,['#91AABC','#CCAA96','#9BC7C2'][j])
   rr(im,(x+106,510,x+130,546),1,'#F5F7FB')
   txt(im,x+6,576,['ΜΟΝΟΚΑΤΟΙΚΙΕΣ','ΟΙΚΟΠΕΔΑ','ΕΠΑΓΓΕΛΜΑΤΙΚΑ'][j],12,'#243A59','black')
 elif typ=='beauty':
  rr(im,(2,65,w-2,h-2),0,'#FCF0F6')
  txt(im,33,87,'FORMA',27,'#352333','black')
  txt(im,w-36,97,'ΥΠΗΡΕΣΙΕΣ    BOOK',14,'#745B71','bold',anchor='rt')
  txt(im,32,185,'Feel good.',54,'#5C3149','black')
  txt(im,32,250,'Look great.',57,'#5C3149','black')
  txt(im,33,343,'Ραντεβού με ένα κλικ',21,'#A46D8B','med')
  rr(im,(33,403,299,462),23,'#9F5B7F');txt(im,56,419,'ΚΛΕΙΣΕ ΡΑΝΤΕΒΟΥ',18,'white','black')
  circle(im,488,401,124,'#E6AFBF')
  circle(im,488,380,74,'#C986A4')
  for j in range(3):rr(im,(33+j*196,528,218+j*196,621),19,['#EDCFDE','#D6BDD6','#F2DADD'][j])
 return im

SHOP=framewindow('ATELIER','shop')
FOOD=framewindow('TERRA','food')
ESTATE=framewindow('REAL ESTATE','estate')
BEAUTY=framewindow('FORMA','beauty')

# Browser takes arbitrary transform (scale/rotation) to simulate real camera motion
def card(im,orig,cx,cy,scale=1,angle=0,opacity=255,shadow=True):
 if opacity<=0 or scale<=0:return
 w=max(2,int(orig.width*scale));h=max(2,int(orig.height*scale))
 if w>1700 or h>1700:return
 aa=orig.resize((w,h),Image.Resampling.BICUBIC)
 if angle:aa=aa.rotate(angle,Image.Resampling.BICUBIC,expand=True)
 x=int(cx-aa.width/2);y=int(cy-aa.height/2)
 if shadow:
  # cheap underlay box plus neon soft underline
  rr(im,(x+11,y+16,x+aa.width+9,y+aa.height+17),27,(0,0,0,91))
 composite_outside(im,aa,x,y)

def badge(im,x,y,text,color='cyan'):
 rr(im,(x,y,x+int(measure(text,16,'bold'))+27,y+34),12,(23,30,58,245),outline=(101,112,164,190),width=1)
 txt(im,x+13,y+6,text,16,color,'bold')

def moving_text(im,t,words,x,y,size=73,stagger=.11,color='white',kind='black',speed=.35):
 # each word is individually animated in from below with spring overshoot
 curr=x
 for i,word in enumerate(words):
  p=spring((t-i*stagger)/speed)
  if t-i*stagger<-.1:p=0
  xx=curr;yy=y+int((1-p)*96)
  if p>.001:txt(im,xx,yy,word,size,color if not isinstance(color,list) else color[i%len(color)],kind,alpha=int(255*clamp((t-i*stagger)/.18)))
  curr+=measure(word+' ',size,kind)

def morph_line(im,t,headline,subline,accent='cyan'):
 p=ease(t/.75)
 y=int(171+(1-p)*85)
 txt(im,44,y,headline,fit(headline,636,67),color='white',kind='black',alpha=int(255*p))
 txt(im,45,y+82,subline,fit(subline,632,49),color=accent,kind='black',alpha=int(255*ease((t-.18)/.5)))

def rounded_rect_anim(im,x0,y0,x1,y1,c,progress=1,rad=12,outline=None):
 p=ease(progress);rr(im,(x0,y0,x0+(x1-x0)*p,y1),rad,c,outline)

def scene_intro(im,t):
 # continuous scale + editorial wipes
 for j in range(4):
  xx=(j*200+int(t*150))%W
  line(im,[(xx,-80),(xx-160,450)],(118,114,255,38),2)
 badge(im,43,155,'ΔΗΜΙΟΥΡΓΙΑ ΧΩΡΙΣ ΚΑΛΟΥΠΙΑ','cyan')
 p=spring((t-.25)/.62)
 txt(im,43,267-(1-p)*95,'Η ΕΠΙΧΕΙΡΗΣΗ',fit('Η ΕΠΙΧΕΙΡΗΣΗ',635,68),'white','black',alpha=int(255*clamp((t-.25)/.18)))
 txt(im,43,347-(1-p)*110,'ΣΟΥ ΕΙΝΑΙ',83,'white','black',alpha=int(255*clamp((t-.4)/.18)))
 p2=spring((t-1.08)/.52)
 txt(im,39,497+(1-p2)*190,'ΜΟΝΑΔΙΚΗ.',fit('ΜΟΝΑΔΙΚΗ.',643,102),'lime','black',alpha=int(255*clamp((t-1.08)/.16)))
 # Progressive animated stencil wipe through multiple rectangles
 for j in range(13):
  k=clamp((t-1.4-j*.025)/.3)
  rr(im,(43+j*48,671,43+j*48+43*k,680),2,'purple')
 p3=ease((t-1.70)/.42)
 txt(im,45,736+(1-p3)*75,'Γιατί να έχει μια',40,'white','med',alpha=int(255*p3))
 txt(im,45,791+(1-p3)*75,'συνηθισμένη ιστοσελίδα;',39,'muted','med',alpha=int(255*p3))
 # Depth frame builds itself from outline and grows into a mini site illustration
 bp=ease((t-2.1)/.85)
 x0=66; y0=941
 rr(im,(x0,y0,x0+int(582*bp),y0+int(200*bp)),24,(28,36,72,230),outline=(109,109,220,int(255*bp)),width=2)
 if bp>.45:
  pp=clamp((bp-.45)/.55)
  txt(im,97,984,'YOUR BRAND.',47,'white','black',int(255*pp))
  rr(im,(99,1063,99+int(242*pp),1096),12,'purple')
  txt(im,109,1069,'YOUR EXPERIENCE',14,'white','bold',int(255*pp))
  line(im,[(430,1008),(602,1008)],(186,193,255,int(170*pp)),6)
  line(im,[(430,1037),(545,1037)],(186,193,255,int(170*pp)),6)

def scene_industries(im,t):
 # frame orbiting, no discrete still slideshow
 morph_line(im,t,'ΔΕΝ ΥΠΑΡΧΕΙ','ΕΝΑ ΣΧΕΔΙΟ ΓΙΑ ΟΛΟΥΣ.','lime')
 txt(im,48,339,'Κάθε κλάδος έχει τη δική του ταυτότητα.',23,'muted','med',alpha=int(255*ease((t-.3)/.6)))
 # carousel on a single continuously moving stage
 stages=[SHOP,FOOD,ESTATE,BEAUTY]
 u=clamp((t-.35)/1.30,0,3.15)
 # continuous movement across the frame with ease around each center, rather than cut to new slides
 for j,panel in enumerate(stages):
  dist=j-u
  if abs(dist)>1.75:continue
  depth=clamp(1-abs(dist)*.30,.58,1)
  scale=depth*.89
  cx=360+dist*435
  cy=713+abs(dist)*55+18*math.sin(t*1.8+j)
  angle=-dist*11
  card(im,panel,cx,cy,scale,angle,int(255*clamp((1.75-abs(dist))/.6)))
 # animated choice indicator and process line
 y=1111
 for i,name in enumerate(['SHOP','FOOD','REAL ESTATE','BEAUTY']):
  x=45+i*160
  rr(im,(x,y,x+148,y+55),17,(31,38,73,250),outline=(88,98,159,135),width=1)
  txt(im,x+74,y+19,name,15,'white','bold',anchor='mt')
  if abs(u-i)<.66:
   rr(im,(x+9,y+47,x+9+int(128*(1-abs(u-i))),y+51),2,'cyan')

def dashboard_panel():
 w,h=628,744
 im=Image.new('RGBA',(w,h),(0,0,0,0))
 rr(im,(1,1,w-2,h-2),29,'#EDF2FA',outline='#8393C1',width=2)
 rr(im,(1,1,w-2,64),29,'#19223E');ImageDraw.Draw(im).rectangle((1,36,w-2,64),fill=rgba('#19223E'))
 circle(im,32,31,6,'cyan');txt(im,51,21,'EAZYFIX / BUSINESS PANEL',17,'white','bold')
 rr(im,(15,79,145,h-20),20,'#24304F')
 for j in range(7):
  rr(im,(31,104+j*73,124,145+j*73),11,('#5960CD' if j==1 else '#32405F'))
  txt(im,43,115+j*73,['HOME','LIST','DATA','EDIT','TEAM','STATS','TOOLS'][j],13,'white','bold')
 txt(im,173,104,'Διαχείριση επιχείρησης',26,'#263552','black')
 txt(im,175,157,'Οργάνωση, αυτοματισμοί & δεδομένα',16,'#74819A','med')
 for j,(v,l) in enumerate([('128','ΚΑΤΑΧΩΡΙΣΕΙΣ'),('24','ΝΕΑ ΑΙΤΗΜΑΤΑ'),('94%','ΠΛΗΡΟΤΗΤΑ')]):
  x=169+j*143
  rr(im,(x,215,x+133,335),16,'white')
  txt(im,x+11,235,v,34,'#4339A6','black')
  txt(im,x+11,292,l,11,'#637089','bold')
 rr(im,(166,359,w-25,577),22,'white')
 txt(im,188,377,'ΚΙΝΗΣΗ / ΑΝΑΦΟΡΕΣ',15,'#68728B','bold')
 for j in range(4):
  y=447+j*36;line(im,[(193,y),(582,y)],(190,199,219,110),1)
 pts=[(203,535),(267,508),(327,524),(393,461),(456,480),(520,423),(578,436)]
 ImageDraw.Draw(im).line(pts,fill=rgba('#6B5CFF'),width=5,joint='curve')
 for x,y in pts:circle(im,x,y,5,'purple')
 rr(im,(167,602,w-25,711),16,'white')
 txt(im,191,623,'ΝΕΟ ΑΙΤΗΜΑ',19,'#222A46','black')
 txt(im,193,660,'Στοιχεία πελάτη  •  Ενέργεια',15,'#818AA1','med')
 rr(im,(491,647,588,688),14,'#C8F6C7');txt(im,506,659,'ΕΝΕΡΓΟ',14,'#276B40','black')
 return im
DASH=dashboard_panel()

def scene_work(im,t):
 # Product design demo: UI moves on-screen and is interacted with
 p=ease(t/.68)
 txt(im,46,180+(1-p)*110,'ΟΧΙ ΜΟΝΟ',75,'white','black',int(255*p))
 txt(im,45,271+(1-p)*110,'ΕΜΦΑΝΙΣΗ.',79,'cyan','black',int(255*p))
 txt(im,45,364,'ΚΑΙ ΛΕΙΤΟΥΡΓΙΕΣ ΠΟΥ ΔΟΥΛΕΥΟΥΝ.',fit('ΚΑΙ ΛΕΙΤΟΥΡΓΙΕΣ ΠΟΥ ΔΟΥΛΕΥΟΥΝ.',629,28),'white','bold',int(255*ease((t-.22)/.5)))
 pc=470+((1-ease((t-.24)/.65))*520)
 # interface does not just fade: travels, scales, simulates interaction and animated data
 sc=.94+.035*math.sin(t*1.8)
 card(im,DASH,359,pc+389,scale=sc,angle=2.4*math.sin(t*.8),opacity=255)
 if t>1.00:
  # moving cursor and active click pulse in UI
  u=ease((t-1.0)/1.25)
  cx=300+u*212
  cy=774-u*98
  d=ImageDraw.Draw(im)
  d.polygon([(cx,cy),(cx+5,cy+26),(cx+12,cy+18),(cx+26,cy+18)],fill=rgba('black'),outline=rgba('white'))
  if t>2.2:
   pulse=(t-2.2)
   if pulse<.65:
    r=5+int(pulse*95);circle(im,cx,cy,r,(0,0,0,0),outline=(89,213,255,int(255*(1-pulse/.65))),width=3)
  # interactive toast slides up
  k=spring((t-2.35)/.55)
  if k>.01:
   y=1019+(1-k)*140
   rr(im,(110,y,627,y+87),20,'#F6FBFD',outline='#74DBB5',width=2)
   circle(im,152,y+45,22,'#C4F6DD')
   txt(im,141,y+27,'✓',31,'#268C61','black')
   txt(im,187,y+18,'Η ΕΝΕΡΓΕΙΑ ΟΛΟΚΛΗΡΩΘΗΚΕ',20,'#263755','bold')
   txt(im,187,y+52,'Έξυπνη διαχείριση, λιγότερος χρόνος.',15,'#697A91','med')

def phone_mockup(w=283,h=606):
 im=Image.new('RGBA',(w,h),(0,0,0,0))
 rr(im,(2,2,w-3,h-3),44,'#14182D',outline='#99A3F5',width=3)
 rr(im,(12,12,w-13,h-13),34,'#F8F9FE')
 rr(im,(83,12,201,36),14,'#14182D')
 rr(im,(12,50,w-13,246),0,'#153D5E')
 txt(im,29,67,'SAMOTHRAKI',21,'white','black')
 txt(im,29,119,'Ο δικός σου',27,'white','bold')
 txt(im,29,157,'χώρος.',42,'#BBF2FF','black')
 rr(im,(27,211,256,254),12,'white')
 txt(im,40,223,'Αναζήτηση ακινήτου  ⌕',15,'#5D7399','med')
 txt(im,27,281,'ΝΕΑ ΑΚΙΝΗΤΑ',18,'#233550','black')
 for j in range(2):
  y=321+j*118
  rr(im,(23,y,w-22,y+104),13,'#E8EFF8')
  rr(im,(30,y+9,126,y+93),12,['#CADCDA','#E4D7C8'][j])
  ImageDraw.Draw(im).polygon([(40,y+61),(77,y+29),(116,y+61)],fill=rgba('#7898A2'))
  rr(im,(48,y+61,102,y+94),2,'#A1BCC3')
  txt(im,140,y+17,['Μονοκατοικία','Οικόπεδο'][j],16,'#2C3951','bold')
  txt(im,141,y+52,'Σαλαμίνα',13,'#728097','med')
  txt(im,141,y+74,['120 τ.μ.','300 τ.μ.'][j],13,'#514BCD','bold')
 rr(im,(82,559,203,566),5,'#CBD1E7')
 return im
PHONE=phone_mockup()

def scene_responsive(im,t):
 p=ease(t/.75)
 txt(im,45,186+(1-p)*80,'ΣΧΕΔΙΑΣΜΕΝΗ',fit('ΣΧΕΔΙΑΣΜΕΝΗ',635,71),'white','black',int(255*p))
 txt(im,46,276+(1-p)*70,'ΓΙΑ ΚΑΘΕ ΟΘΟΝΗ.',fit('ΓΙΑ ΚΑΘΕ ΟΘΟΝΗ.',635,76),'lime','black',int(255*p))
 txt(im,46,376,'Desktop  /  Tablet  /  Mobile',25,'muted','med',int(255*ease((t-.25)/.5)))
 # windows visibly morph / move behind responsive device
 u=ease((t-.4)/1.0)
 cx=318-(u*66);cy=735
 card(im,ESTATE,cx,cy,scale=.78-.20*u,angle=-7+5*u)
 # Mobile slides from right while rotating and scaling into place
 v=spring((t-1.22)/.77)
 cx2=850-363*v
 cy2=840-30*v
 card(im,PHONE,cx2,cy2,.83+.12*v,angle=-16*(1-v)+4,opacity=int(255*clamp((t-1.18)/.3)))
 # moving bracket and connecting line; interactions emphasize continuous resizing
 d=ImageDraw.Draw(im)
 dash=(t*60)%40
 for j in range(6):
  y=523+j*35+dash
  d.line((647,y,647,y+16),fill=rgba('cyan',90),width=2)
 if t>2.2:
  k=ease((t-2.2)/.45)
  rr(im,(68,1092,651,1164),19,'#192647',outline=(69,102,175,155))
  txt(im,103,1112,'ΜΙΑ ΕΜΠΕΙΡΙΑ. ΠΑΝΤΟΥ.',29,'white','black',int(255*k))

# Actual wrench mark from the EazyFix site's public favicon.svg (vector-derived)
from io import BytesIO
import cairosvg
LOGO_SVG="""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4f46e5"/><stop offset="1" stop-color="#6d28d9"/></linearGradient></defs><rect width="64" height="64" rx="16" fill="url(#g)"/><g transform="translate(16 16) scale(1.333)" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></g></svg>"""
LOGO_IMAGE=Image.open(BytesIO(cairosvg.svg2png(bytestring=LOGO_SVG.encode(),output_width=420,output_height=420))).convert('RGBA')
def logo(im,cx,cy,s=90,rotation=0):
 s=int(s)
 if s<=1:return
 icon=LOGO_IMAGE.resize((s,s),Image.Resampling.LANCZOS)
 composite_outside(im,icon,int(cx-s/2),int(cy-s/2))

def scene_outro(im,t):
 # central orbit animation + animated type and on-brand URL
 k=ease(t/.75)
 cx,cy=360,326
 d=ImageDraw.Draw(im)
 for j in range(3):
  a=j*80+t*48
  r=int(131+32*j+15*math.sin(t*1.1+j))
  d.arc((cx-r,cy-r,cx+r,cy+r),a,a+210,fill=rgba(['cyan','purple2','lime'][j],int(130*k)),width=2)
 for i in range(25):
  ang=i*2*math.pi/25+t*.42
  r=175+15*math.sin(t+i)
  circle(im,cx+r*math.cos(ang),cy+r*math.sin(ang),2,['cyan','purple2'][i%2])
 if k>.01:
  logo(im,360,320,133*k)
  txt(im,360,472+(1-k)*54,'EazyFix',86,'white','black',int(255*k),anchor='mt')
 p=spring((t-.50)/.62)
 txt(im,360,640+(1-p)*95,'ΙΣΤΟΣΕΛΙΔΕΣ',fit('ΙΣΤΟΣΕΛΙΔΕΣ',636,75),'white','black',int(255*clamp((t-.5)/.2)),anchor='mt')
 txt(im,360,725+(1-p)*95,'ΣΤΑ ΜΕΤΡΑ ΣΟΥ.',fit('ΣΤΑ ΜΕΤΡΑ ΣΟΥ.',633,74),'lime','black',int(255*clamp((t-.67)/.2)),anchor='mt')
 txt(im,360,843,'Στείλε μου την ιδέα σου.',30,'lav','med',int(255*ease((t-1)/.55)),anchor='mt')
 v=spring((t-1.23)/.6)
 rr(im,(65,944+(1-v)*130,655,1045+(1-v)*130),28,'purple',outline='#9994FF',width=2)
 txt(im,360,965+(1-v)*130,'eazyfix.gr',54,'white','black',int(255*clamp((t-1.24)/.2)),anchor='mt')
 if t>2.0:
  txt(im,360,1095,'WEB DESIGN   •   WEB APPS   •   CUSTOM SOLUTIONS',17,'muted','bold',anchor='mt')

def segment_render(im,t):
 if t<3.4:scene_intro(im,t)
 elif t<9.1:scene_industries(im,t-3.4)
 elif t<15.2:scene_work(im,t-9.1)
 elif t<19.4:scene_responsive(im,t-15.2)
 else:scene_outro(im,t-19.4)

def render(t):
 im=background(t)
 segment_render(im,t)
 # edge wipes and impact flash between chapters; a 7-frame dynamic transition
 for moment in [3.4,9.1,15.2,19.4]:
  d=abs(t-moment)
  if d<.19:
   layer=Image.new('RGBA',(W,H));ld=ImageDraw.Draw(layer)
   w=int((.19-d)/.19*W*1.6)
   ld.polygon([(0,0),(w,0),(w-240,H),(0,H)],fill=(128,113,255,int(165*(.19-d)/.19)))
   im.alpha_composite(layer)
   if d<.055:
    im=Image.blend(im,Image.new('RGBA',(W,H),'white'),.14*(1-d/.055))
 topbar(im,t,chapter='ΕΞΑΤΟΜΙΚΕΥΜΕΝΕΣ ΙΣΤΟΣΕΛΙΔΕΣ')
 return im.convert('RGB')

# Synthesized original music: dry electronic rhythm + modulated chords + sound design accents
def make_music():
 sr=44100
 n=int(sr*(DURATION+.6))
 rng=np.random.default_rng(15)
 a=np.zeros((n,2),dtype=np.float32)
 def add(start,snd,vol=1,pan=0):
  ix=int(start*sr)
  if ix<0:return
  length=min(len(snd),n-ix)
  if length<=0:return
  s=snd[:length]*vol
  if s.ndim==1:
   a[ix:ix+length,0]+=s*(1-pan*.43)
   a[ix:ix+length,1]+=s*(1+pan*.43)
  else:a[ix:ix+length]+=s
 def kick():
  tt=np.arange(int(sr*.52))/sr
  f=48+130*np.exp(-tt*23)
  ph=np.cumsum(f)/sr*2*np.pi
  return np.sin(ph)*np.exp(-tt*12)+rng.normal(0,.2,len(tt))*np.exp(-tt*72)
 def snare():
  tt=np.arange(int(sr*.26))/sr
  noise=rng.normal(0,1,len(tt))
  noise=(noise-np.convolve(noise,np.ones(50)/50,mode='same'))
  return noise*np.exp(-tt*20)*.45+np.sin(2*np.pi*192*tt)*np.exp(-tt*25)*.25
 def hh():
  tt=np.arange(int(sr*.11))/sr
  noise=rng.normal(0,1,len(tt)); noise=noise-np.convolve(noise,np.ones(12)/12,mode='same')
  return noise*np.exp(-tt*43)*.16
 beat=60/126
 k=kick();sn=snare()
 for i in range(int(DURATION/beat)+3):
  b=i*beat
  if b>=DURATION:break
  add(b,k,.45)
  if i%2==1:add(b,sn,.38)
  for j in range(2):
   t=b+j*beat/2
   if t<DURATION:add(t,hh(),.34 if j else .5,(-1 if j else 1)*.3)
 # filtered saw/sine bass: original minor progression
 roots=[55,46.249,61.735,51.913]
 for bar in range(int(DURATION/(beat*4))+1):
  root=roots[bar%4]
  for kidx in range(4):
   st=bar*beat*4+kidx*beat
   if st>=DURATION:break
   tt=np.arange(int(sr*.37))/sr
   env=(1-np.exp(-tt*125))*np.exp(-tt*6)
   f=root*(1 if kidx!=3 else 2)
   snd=(np.sin(2*np.pi*f*tt)+.18*np.sin(2*np.pi*f*2*tt))*env*.24
   add(st,snd)
 # melodic percussive digital plucks
 notes=[(220,261.63,329.63,392),(174.61,220,261.63,349.23),(246.94,293.66,369.99,440),(196,246.94,293.66,392)]
 for i in range(int(DURATION/(beat/2))+1):
  st=i*beat/2
  if st>=DURATION:break
  keys=notes[(i//8)%4];fr=keys[(i*3)%4]*(2 if i%4==0 else 1)
  tt=np.arange(int(sr*.39))/sr
  tone=(np.sin(2*np.pi*fr*tt)+.22*np.sin(2*np.pi*fr*2*tt))*(1-np.exp(-tt*75))*np.exp(-tt*10)
  add(st+.07,tone,.095,(-1 if i%2 else 1)*.5)
 # pads behind music
 for j in range(int(DURATION/(beat*4))+1):
  st=j*beat*4
  if st>=DURATION:break
  freqs=notes[j%4][:3]
  tt=np.arange(int(sr*min(2.2,DURATION-st)))/sr
  env=np.minimum(1,tt*6)*np.minimum(1,np.maximum(0,(len(tt)/sr-tt)*1.8))
  pad=sum(np.sin(2*np.pi*(f*.5)*tt+np.sin(2*np.pi*.18*tt)*.3) for f in freqs)/len(freqs)
  add(st,pad*env,.07)
 # WHOOSHES / impacts exactly synced to visual cuts
 for st in [0,1.07,3.38,9.08,15.18,19.38]:
  tt=np.arange(int(sr*.38))/sr
  nz=rng.normal(0,1,len(tt));nz=np.cumsum(nz)*.001
  # high-energy airy ramp->down, stereo displacement
  env=np.sin(np.pi*np.clip(tt/.38,0,1))**1.5
  sweep=(nz*.32+rng.normal(0,.2,len(tt)))*env
  add(st-.15,sweep,.25,pan=-.45)
  it=np.arange(int(sr*.18))/sr
  impact=(np.sin(2*np.pi*(85-45*it)*it)*np.exp(-it*27)+rng.normal(0,.2,len(it))*np.exp(-it*38))
  add(st,impact,.28)
 # outro quieter around last 1 sec, avoid clipping
 tt=np.arange(n)/sr
 a*=np.clip((DURATION-tt)/.68,0,1)[:,None]
 maxv=np.max(np.abs(a))
 a=(a/maxv*.88).astype('float32')
 path=AS/'eazyfix_v2_music.wav'
 wavfile.write(path,sr,(a*32767).astype(np.int16))
 return path

def frames_poster():
 moments=[.9,2.0,4.5,6.0,8.0,9.8,12.5,16.7,20.7,22.3]
 tiles=[]
 for t in moments:
  im=render(t);im.thumbnail((270,480));tiles.append(im)
 sheet=Image.new('RGB',(270*5,480*2),'#0D1022')
 for idx,im in enumerate(tiles):sheet.paste(im,((idx%5)*270,(idx//5)*480))
 sheet.save(AS/'eazyfix_v2_contact_sheet.jpg',quality=89)
 render(21.2).save(AS/'eazyfix_v2_cover.jpg',quality=94)

if __name__=='__main__':
 mode=sys.argv[1] if len(sys.argv)>1 else 'full'
 t0=time.time()
 if mode=='test':
  frames_poster();print('TEST_SHEET',time.time()-t0,flush=True)
 else:
  music=make_music()
  cmd=['ffmpeg','-y','-hide_banner','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-i',str(music),'-vf','format=yuv420p','-c:v','libx264','-crf','18','-preset','ultrafast','-movflags','+faststart','-r',str(FPS),'-c:a','aac','-b:a','192k','-shortest',str(OUT/'EazyFix_Pro_Motion_Ad.mp4')]
  log=open(AS/'eazyfix_render_v2.log','wb')
  p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT)
  try:
   for i in range(N):
    t=i/FPS
    im=render(t)
    p.stdin.write(im.tobytes())
    if i%90==0:print('progress',i,N,round(time.time()-t0,1),flush=True)
  finally:
   if p.stdin:p.stdin.close()
  ret=p.wait();log.close();err=(AS/'eazyfix_render_v2.log').read_text(errors='replace')
  print('ENCODE_RET',ret,'TIME',time.time()-t0,'ERR',err[-1500:],flush=True)
  if ret==0:
   frames_poster()
   print('FILE',OUT/'EazyFix_Pro_Motion_Ad.mp4',flush=True)
