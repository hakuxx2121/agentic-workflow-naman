import json,urllib.request,urllib.parse,io,os
from PIL import Image
H={'User-Agent':'tvhome-builder/1.0 (personal)'}
T=["File:Lake-sherburne-964855.jpg","File:Moraine Lake 17092005.jpg","File:Parc de la Chute-Montmorency 001.jpg","File:Spruce forest at Holma.jpg","File:Komos site baie Crète.jpg","File:Yosemite by Carol M. Highsmith.jpg","File:Oolah Valley (16089307144).jpg","File:Juan Griego Sunset.jpg"]
os.makedirs('../app/src/main/res/drawable-nodpi',exist_ok=True)
cred=["Wallpaper credits (all from Wikimedia Commons, CC0 or public domain)\n"]
for i,t in enumerate(T):
  q={'action':'query','format':'json','titles':t,'prop':'imageinfo','iiprop':'url|extmetadata','iiurlwidth':2560}
  p=list(json.load(urllib.request.urlopen(urllib.request.Request('https://commons.wikimedia.org/w/api.php?'+urllib.parse.urlencode(q),headers=H)))['query']['pages'].values())[0]
  ii=p['imageinfo'][0];m=ii['extmetadata']
  im=Image.open(io.BytesIO(urllib.request.urlopen(urllib.request.Request(ii['thumburl'],headers=H)).read())).convert('RGB')
  w,h=im.size;s=max(1920/w,1080/h);im=im.resize((round(w*s),round(h*s)),Image.LANCZOS)
  w,h=im.size;l=(w-1920)//2;tp=(h-1080)//2;im=im.crop((l,tp,l+1920,tp+1080))
  f=f'../app/src/main/res/drawable-nodpi/wp_{i+1}.jpg';im.save(f,'JPEG',quality=80,optimize=True)
  import re;art=re.sub('<[^>]+>','',m.get('Artist',{}).get('value','')).strip()
  cred.append(f"wp_{i+1}.jpg  {t[5:]}\n  Source: {ii['descriptionurl']}\n  Author: {art}\n  License: {m.get('LicenseShortName',{}).get('value','')}\n")
open('../WALLPAPER_CREDITS.txt','w').write("\n".join(cred))
