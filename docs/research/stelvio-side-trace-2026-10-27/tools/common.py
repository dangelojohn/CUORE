import math
# photo-crop coordinate system: crop box (420,540,1940,1200) of the original download
FW=(219.0,446.0,118.0)   # front wheel centre x,y and tyre radius (crop px)
RW=(1116.0,499.0,129.0)  # rear wheel
AX_F,AX_R,WY,TR = 199.0,650.0,269.0,59.0   # drawing frame (existing)
NOSE_X,TAIL_X = 28.0,1492.0                 # photo extremes (crop px)
DNOSE,DTAIL = 57.0,801.0                    # drawing bbox x extremes (existing)
_k=(RW[2]-FW[2])/(RW[0]-FW[0])
def _r(x): return FW[2]+_k*(x-FW[0])
def _yc(x): return FW[1]+(RW[1]-FW[1])*(x-FW[0])/(RW[0]-FW[0])
def _nat(x): return AX_F+(TR/_k)*math.log(_r(x)/FW[2])
_nf,_nr,_nn,_nt=_nat(FW[0]),_nat(RW[0]),_nat(NOSE_X),_nat(TAIL_X)
def T(x,y):
    """photo-crop px -> drawing units (perspective-levelled, axles pinned)."""
    n=_nat(x)
    if n<_nf: X=DNOSE+(n-_nn)*(AX_F-DNOSE)/(_nf-_nn)
    elif n<=_nr: X=AX_F+(n-_nf)*(AX_R-AX_F)/(_nr-_nf)
    else: X=AX_R+(n-_nr)*(DTAIL-AX_R)/(_nt-_nr)
    return X, WY+(y-_yc(x))*TR/_r(x)
if __name__=='__main__':
    print('natural wheelbase',_nr-_nf,'nose stretch',(AX_F-DNOSE)/(_nf-_nn),'mid',(AX_R-AX_F)/(_nr-_nf),'tail',(DTAIL-AX_R)/(_nt-_nr))
    for p in [(30,300),(1000,30),(219,566),(1116,627),(350,512),(1335,546)]: print(p,T(*p))
