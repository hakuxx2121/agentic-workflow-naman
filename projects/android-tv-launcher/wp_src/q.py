import json,urllib.request,urllib.parse
H={'User-Agent':'tvhome-builder/1.0 (personal)'}
out=[]
for term in ["Yosemite","Grand Teton","national park","Glacier National Park","Alaska","Iceland","sunset beach"]:
  q={'action':'query','format':'json','generator':'search','gsrnamespace':6,'gsrsearch':term+' incategory:"Featured_pictures_on_Wikimedia_Commons"','gsrlimit':40,'prop':'imageinfo','iiprop':'url|size|extmetadata','iiurlwidth':1920}
  d=json.load(urllib.request.urlopen(urllib.request.Request('https://commons.wikimedia.org/w/api.php?'+urllib.parse.urlencode(q),headers=H)))
  for p in d.get('query',{}).get('pages',{}).values():
    ii=p['imageinfo'][0];m=ii['extmetadata'];lic=m.get('LicenseShortName',{}).get('value','')
    if ('CC0' in lic or 'ublic domain' in lic) and ii['width']>ii['height']*1.3 and ii['width']>=1920:
      out.append((term,p['title'],lic,ii['descriptionurl'],ii['thumburl']))
for o in out: print(json.dumps(o))
