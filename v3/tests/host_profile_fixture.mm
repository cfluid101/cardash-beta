#import "HostProfile.h"
#import <objc/runtime.h>
#include <unistd.h>

static NSString *Mode;
static NSUInteger Initializations;
static void Require(BOOL value,const char *message){if(!value){fprintf(stderr,"%s\n",message);exit(1);}}

@interface CDHost16:NSObject<NSSecureCoding>
@property(nonatomic,copy) NSString *displayName;
@property(nonatomic,copy) NSArray *wiredIPv6Addresses;
@property(nonatomic,copy) NSArray *wirelessIPv6Addresses;
@property(nonatomic) long long port;
@property(nonatomic,copy) NSString *carplayWiFiUUID;
@property(nonatomic,copy) NSString *deviceIdentifier;
@property(nonatomic,strong) id publicKey;
@property(nonatomic,copy) NSString *sourceVersion;
@property(nonatomic,getter=isWiredCarPlaySimulator) bool wiredCarPlaySimulator;
- (id)initWithHostProperties:(NSDictionary *)properties;
@end
@implementation CDHost16
// macOS Intel BOOL is char; this private iOS ABI encodes BOOL as B.
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wmismatched-return-types"
+(bool)supportsSecureCoding{return ![Mode isEqual:@"secure-disabled"];}
#pragma clang diagnostic pop
-(id)initWithHostProperties:(NSDictionary *)p {
    Initializations++;
    Require(p.count==8,"Unexpected dictionary key count");
    Require([p[@"wiredIPAddresses"] isEqual:@[@"::1"]]&&[p[@"wirelessIPAddresses"] isEqual:@[]],"Wrong address dictionary keys");
    Require([p[@"deviceID"] isEqual:@"02:43:44:4c:41:42"],"Wrong identity dictionary key");
    Require(!p[@"wiredIPv6Addresses"]&&!p[@"deviceIdentifier"]&&!p[@"carplayWiFiUUID"],"Accessor key or nil sentinel sent");
    if((self=[super init])){
        _displayName=p[@"displayName"];_wiredIPv6Addresses=p[@"wiredIPAddresses"];
        _wirelessIPv6Addresses=p[@"wirelessIPAddresses"];_port=[p[@"port"] longLongValue];
        _deviceIdentifier=p[@"deviceID"];_publicKey=p[@"publicKey"];
        _sourceVersion=p[@"sourceVersion"];_wiredCarPlaySimulator=[p[@"wiredCarPlaySimulator"] boolValue];
        if([Mode isEqual:@"corrupt-live"])_deviceIdentifier=@"another host";
        if([Mode isEqual:@"wrong-live-type"])_publicKey=[_publicKey dataUsingEncoding:NSUTF8StringEncoding];
    }return self;
}
-(void)encodeWithCoder:(NSCoder *)coder {
    if([Mode isEqual:@"archive-throws"])@throw [NSException exceptionWithName:@"FixtureArchiveFailure" reason:@"test" userInfo:nil];
    [coder encodeObject:self.displayName forKey:@"displayName"];
    [coder encodeObject:self.wiredIPv6Addresses forKey:@"wiredIPAddresses"];
    [coder encodeObject:self.wirelessIPv6Addresses forKey:@"wirelessIPAddresses"];
    [coder encodeInteger:self.port forKey:@"port"];
    [coder encodeObject:self.deviceIdentifier forKey:@"deviceID"];
    [coder encodeObject:self.publicKey forKey:@"publicKey"];
    [coder encodeObject:self.sourceVersion forKey:@"sourceVersion"];
    [coder encodeObject:@(self.wiredCarPlaySimulator) forKey:@"wiredCarPlaySimulator"];
}
-(id)initWithCoder:(NSCoder *)coder {
    if((self=[super init])){
        NSSet *arrays=[NSSet setWithObjects:NSArray.class,NSString.class,nil];
        _displayName=[coder decodeObjectOfClass:NSString.class forKey:@"displayName"];
        _wiredIPv6Addresses=[coder decodeObjectOfClasses:arrays forKey:@"wiredIPAddresses"];
        _wirelessIPv6Addresses=[coder decodeObjectOfClasses:arrays forKey:@"wirelessIPAddresses"];
        _port=[coder decodeIntegerForKey:@"port"];
        _deviceIdentifier=[coder decodeObjectOfClass:NSString.class forKey:@"deviceID"];
        _publicKey=[coder decodeObjectOfClass:NSString.class forKey:@"publicKey"];
        _sourceVersion=[coder decodeObjectOfClass:NSString.class forKey:@"sourceVersion"];
        _wiredCarPlaySimulator=[[coder decodeObjectOfClass:NSNumber.class forKey:@"wiredCarPlaySimulator"] boolValue];
        if([Mode isEqual:@"corrupt-wire"])_port++;
        if([Mode isEqual:@"wrong-wire-type"])_publicKey=[_publicKey dataUsingEncoding:NSUTF8StringEncoding];
    }return self;
}
@end

@interface CDLegacyHost:NSObject @end
@implementation CDLegacyHost
+(void)initialize{_exit(91);}
-(id)initWithDisplayName:(id)n wiredIPv6Addresses:(id)w wirelessIPv6Addresses:(id)r port:(long long)p carplayWiFiUUID:(id)u deviceIdentifier:(id)i publicKey:(id)k sourceVersion:(id)v wiredCarPlaySimulator:(bool)s{_exit(92);}
@end
@interface CDClient:NSObject @end
@implementation CDClient
+(void)initialize{_exit(93);}
-(void)startSessionWithHost:(id)host completion:(void(^)(BOOL,NSError *))completion{_exit(94);}
-(void)cancelRequests{_exit(95);}
@end
@interface CDStatus:NSObject @end
@implementation CDStatus
+(void)initialize{_exit(96);}
-(id)currentSession{_exit(97);}
@end

static NSDictionary *Context(NSString *uuid,NSString *build,BOOL legacy) {
    NSString *path=@"/System/Library/PrivateFrameworks/CarKit.framework/CarKit";
    return @{@"build":build,@"os_version":@"16.0",@"legacy_completion":@{
        @"framework_uuid":uuid,@"class_image":path,@"implementation_image":path,
        @"typed_completion_enabled":@(legacy),@"basis":@"retained_legacy_basis",
        @"daemon_file":@{@"available":@NO}}};
}
static id WrongMethod(id self,SEL selector){(void)self;(void)selector;_exit(98);}
int main(int argc,char **argv){@autoreleasepool{
    Require(argc==2,"Missing mode");Mode=@(argv[1]);
    NSString *uuid=@"56E68CC1-FF26-3491-9ECA-D6974006E1A4";
    Class host=objc_getClass("CDHost16"),client=objc_getClass("CDClient"),status=objc_getClass("CDStatus");
    if([Mode hasPrefix:@"profile-"]){
        NSDictionary *context=Context(uuid,@"20A357",NO);NSString *expected=@"unsupported";
        if([Mode isEqual:@"profile-new"]){expected=@"ios16_0_20A357_arm64e_carkit";}
        else if([Mode isEqual:@"profile-legacy"]){host=objc_getClass("CDLegacyHost");context=Context(@"E7918412-DF06-3E57-9E4E-C031AD370605",@"20G75",YES);expected=@"legacy_ios16_6";}
        else if([Mode isEqual:@"profile-unknown"]){context=Context(@"UNKNOWN",@"20A357",NO);}
        else if([Mode isEqual:@"profile-different-build"]){NSMutableDictionary *changed=[Context(uuid,@"ANOTHER_BUILD",NO) mutableCopy];changed[@"os_version"]=@"ANOTHER_VERSION";context=changed;expected=@"ios16_0_20A357_arm64e_carkit";}
        else if([Mode isEqual:@"profile-legacy-unverified"]){host=objc_getClass("CDLegacyHost");context=Context(@"E7918412-DF06-3E57-9E4E-C031AD370605",@"20G75",NO);}
        else if([Mode isEqual:@"profile-wrong-start-type"]){Class bad=objc_allocateClassPair(client,"WrongClient",0);class_addMethod(bad,@selector(startSessionWithHost:completion:),(IMP)WrongMethod,"v32@0:8@16@24");objc_registerClassPair(bad);client=bad;}
        else Require(NO,"Unknown profile scenario");
        NSDictionary *profile=CDV3FixtureHostProfile(host,client,status,context);
        if(![profile[@"selected_profile"] isEqual:expected])fprintf(stderr,"%s\n",profile.description.UTF8String);
        Require([profile[@"selected_profile"] isEqual:expected],"Incorrect profile selection");
        if([Mode isEqual:@"profile-new"]){
            NSDictionary *completion=profile[@"completion_identity"];
            Require([completion[@"typed_completion_enabled"] boolValue],"Direct completion evidence was not accepted");
            Require(![completion[@"daemon_identity_used_for_callback_abi"] boolValue]&&![completion[@"daemon_implementation_inspected"] boolValue],"Daemon evidence overstated");
            Require([completion[@"retained_block_signature"] isEqual:@"v20@?0B8@\"NSError\"12"],"Wrong block ABI");
        }
        if([Mode isEqual:@"profile-legacy"])Require([profile[@"completion_identity"] isEqual:context[@"legacy_completion"]],"Legacy evidence changed");
        Require(Initializations==0,"Inspector constructed host");
    }else{
        NSString *key=[@"ab" stringByPaddingToLength:64 withString:@"ab" startingAtIndex:0];NSError *error=nil;
        if([Mode isEqual:@"wrong-method-type"]){Class bad=objc_allocateClassPair(host,"WrongHost",0);class_addMethod(bad,@selector(port),(IMP)WrongMethod,"@16@0:8");objc_registerClassPair(bad);host=bad;}
        if([Mode isEqual:@"invalid-key-type"])key=(id)[key dataUsingEncoding:NSUTF8StringEncoding];
        if([Mode isEqual:@"invalid-key-hex"])key=[key uppercaseString];
        id value=[Mode isEqual:@"production-owner-reject"]?CDV3CreateDictionaryHost(host,62000,key,&error):CDV3CreateDictionaryHostFixture(host,62000,key,&error);
        if([Mode isEqual:@"valid"]){if(error)fprintf(stderr,"%s\n",error.description.UTF8String);Require(value!=nil&&error==nil,"Valid host rejected");Require(Initializations==1,"Wrong initialization count");}
        else{
            Require(value==nil&&error!=nil,"Invalid host accepted");
            if([Mode isEqual:@"wrong-method-type"]||[Mode hasPrefix:@"invalid-key"]||[Mode isEqual:@"production-owner-reject"])
                Require(Initializations==0,"Rejected input reached constructor");
        }
    }
    puts("OK");return 0;
}}
