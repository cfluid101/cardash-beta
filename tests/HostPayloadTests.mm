#import "HostPayload.h"
@interface WireHostFixture:NSObject<NSSecureCoding>
@property(nonatomic,strong) id publicKey;
@end
@implementation WireHostFixture
+(BOOL)supportsSecureCoding{return YES;}
-(void)encodeWithCoder:(NSCoder *)coder{[coder encodeObject:self.publicKey forKey:@"publicKey"];}
-(instancetype)initWithCoder:(NSCoder *)coder{if((self=[super init]))_publicKey=[coder decodeObjectOfClass:NSString.class forKey:@"publicKey"];return self;}
@end
static void Require(BOOL ok,const char *message){if(!ok){fprintf(stderr,"%s\n",message);exit(1);}}
int main(void){@autoreleasepool{
    unsigned char bytes[32];for(unsigned i=0;i<32;i++)bytes[i]=i;
    NSData *data=[NSData dataWithBytes:bytes length:32];NSString *encoded=CDPublicKeyString(data);
    Require([encoded isEqual:@"000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"],"public-key encoding mismatch");
    Require(CDPublicKeyString([NSData dataWithBytes:bytes length:31])==nil,"incorrect key length accepted");
    WireHostFixture *host=[WireHostFixture new];host.publicKey=data;NSError *error=nil;
    Require(CDSecureHostRoundTrip(host,&error)==nil&&error!=nil,"legacy NSData unexpectedly accepted as NSString");
    host.publicKey=encoded;error=nil;WireHostFixture *decoded=CDSecureHostRoundTrip(host,&error);
    Require(decoded&&error==nil&&[decoded.publicKey isEqual:encoded],"string key did not survive secure coding");
    host.publicKey=nil;decoded=CDSecureHostRoundTrip(host,&error);Require(decoded&&error==nil&&decoded.publicKey==nil,"nil key did not survive secure coding");
    puts("Host wire-format regression checks passed");return 0;
}}
