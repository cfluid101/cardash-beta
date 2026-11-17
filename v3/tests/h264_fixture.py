"""Small independently generated SPS records; contains no captured device data."""

def configuration(width=1280,height=720,*,profile=100,chroma=1,interlaced=False):
    bits=[]
    def put(value,count):bits.extend((value>>n)&1 for n in range(count-1,-1,-1))
    def ue(value):
        value+=1;count=value.bit_length();put(0,count-1);put(value,count)
    put(profile,8);put(0,8);put(31,8);ue(0)
    if profile in (100,110,122,244):
        ue(chroma)
        if chroma==3:put(0,1)
        ue(0);ue(0);put(0,1);put(0,1)
    ue(0);ue(0);ue(0);ue(1);put(0,1)
    frame_only=not interlaced;unit_y=(1 if chroma in (0,2,3) else 2)*(1 if frame_only else 2);unit_x=2 if chroma in (1,2) else 1
    coded_w=(width+15)//16*16;block_h=16*(1 if frame_only else 2);coded_h=(height+block_h-1)//block_h*block_h
    assert (coded_w-width)%unit_x==0 and (coded_h-height)%unit_y==0
    ue(coded_w//16-1);ue(coded_h//block_h-1);put(int(frame_only),1)
    if not frame_only:put(0,1)
    put(1,1);cropped=coded_w!=width or coded_h!=height;put(int(cropped),1)
    if cropped:
        ue(0);ue((coded_w-width)//unit_x);ue(0);ue((coded_h-height)//unit_y)
    put(0,1);put(1,1)
    while len(bits)%8:put(0,1)
    raw=bytes(sum(bits[i+j]<<(7-j) for j in range(8)) for i in range(0,len(bits),8));escaped=bytearray();zeros=0
    for b in raw:
        if zeros>=2 and b<=3:escaped.append(3);zeros=0
        escaped.append(b);zeros=zeros+1 if b==0 else 0
    sps=b'\x67'+bytes(escaped);pps=b'\x68\xee';return bytes([1,profile,0,31,255,225])+len(sps).to_bytes(2,'big')+sps+b'\x01'+len(pps).to_bytes(2,'big')+pps
