"""Reproducible native graph icon from original geometric primitives."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'.desktop-build/python-packages'))
from PIL import Image,ImageDraw
folder=ROOT/'desktop/icons';folder.mkdir(exist_ok=True)
svg='<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256"><rect width="256" height="256" rx="52" fill="#181b1a"/><path d="M64 68V188 M64 68L188 128L64 188 M64 128H188" fill="none" stroke="#75cbbb" stroke-width="12" stroke-linejoin="round"/>' + ''.join(f'<circle cx="{x}" cy="{y}" r="18" fill="#c1eee1"/>' for x,y in ((64,68),(64,128),(64,188),(188,128)))+'</svg>'
(folder/'icon.svg').write_text(svg,encoding='utf-8')
image=Image.new('RGBA',(1024,1024));draw=ImageDraw.Draw(image);draw.rounded_rectangle((0,0,1023,1023),radius=208,fill='#181b1a')
for points in (((64,68),(64,188)),((64,68),(188,128),(64,188)),((64,128),(188,128))):draw.line([(x*4,y*4) for x,y in points],fill='#75cbbb',width=48,joint='curve')
for x,y in ((64,68),(64,128),(64,188),(188,128)):draw.ellipse(((x-18)*4,(y-18)*4,(x+18)*4,(y+18)*4),fill='#c1eee1')
image=image.resize((256,256),Image.Resampling.LANCZOS);image.save(folder/'icon.png');image.save(folder/'icon.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
