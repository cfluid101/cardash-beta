#define CDV3_LOOPBACK_TEST 1
#import "../native/Loopback.mm"
#include <cassert>
#include <cstdio>

@interface CARSessionRequestHost : NSObject <CDV3LoopbackHost>
@property(nonatomic,strong) NSString *displayName;
@property(nonatomic,strong) NSString *deviceIdentifier;
@property(nonatomic,strong) NSArray *wiredIPv6Addresses;
@property(nonatomic) long long port;
@property(nonatomic) BOOL isWiredCarPlaySimulator;
@end
@implementation CARSessionRequestHost
@end

static bool audioOwn=false;
static unsigned audioCalls=0;
static const void *audioHelper=nullptr;
extern "C" void CDV3AudioHost(const void *helper,bool own) {audioCalls++;if(own||audioHelper==helper){audioHelper=own?helper:nullptr;audioOwn=own;}}

static bool scoped, throwUpdate, cancelHost, consumeHelper, helperDestroyed;
static unsigned updates, events;
@interface HarnessHelper : NSObject
@property(nonatomic,strong) NSMutableData *storage;
@end
@implementation HarnessHelper
- (instancetype)init {
    if ((self=[super init])) self.storage=[NSMutableData dataWithLength:0x200];
    return self;
}
- (void)dealloc {
    // The last native reference is released inside FakeEvent. Destruction must
    // wait until Event restores the selected transport after that callback.
    assert(*(uint32_t *)((uint8_t *)self.storage.mutableBytes+0xb8)==1);
    helperDestroyed=true;
}
@end
static void *Storage(CFTypeRef helper) { return ((__bridge HarnessHelper *)helper).storage.mutableBytes; }
static int32_t FakeUpdate(CFTypeRef helper) {
    auto s=(uint8_t *)Storage(helper); ++updates;
    if (scoped) {
        assert(s[0x40]==1 && s[0x68]==0);
        assert(CFEqual(*(CFStringRef *)(s+0x50),CFSTR("lo0")));
        assert(*(uint32_t *)(s+0x58)==8);
        assert(*(double *)(s+0x48)==1234.0);
        auto map=*(CFDictionaryRef *)(s+0x98);
        assert(CFDictionaryContainsKey(map,CFSTR("en2")));
        assert(CFEqual(CFDictionaryGetValue(map,CFSTR("lo0")),(__bridge CFArrayRef)@[@"::1"]));
        if (throwUpdate) @throw [NSException exceptionWithName:@"test" reason:nil userInfo:nil];
        *(uint32_t *)(s+0xb8)=1;
    } else {
        assert(s[0x40]==0 && s[0x68]==1);
        assert(CFEqual(*(CFStringRef *)(s+0x50),CFSTR("en2")));
    }
    return -123;
}
static void FakeEvent(void *block) {
    ++events; auto b=(uint8_t *)block; auto helper=*(CFTypeRef *)(b+0x28);
    auto s=(uint8_t *)Storage(helper);
    if (*(int32_t *)(b+0x40)==4 && *(uint32_t *)(s+0xb8)==1) *(void **)(s+0xa8)=nullptr;
    if (cancelHost) *(void **)(s+0xa8)=nullptr;
    if (scoped && !cancelHost) Update(helper);
    if (consumeHelper) {
        assert(CFGetRetainCount(helper)==2);
        CFRelease(helper);
        assert(!helperDestroyed);
    }
}
int main(int argc,char **) { @autoreleasepool {
    GuardedLayout=argc==2;
    DerivedStorage=Storage; OriginalUpdate=FakeUpdate; OriginalEvent=FakeEvent;
    CFTypeRef helper=CFBridgingRetain([HarnessHelper new]);
    auto state=(uint8_t *)Storage(helper);
    alignas(16) uint8_t block[0x80]={};
    auto host=[CARSessionRequestHost new]; host.displayName=@"CarDash V3";
    host.deviceIdentifier=@"02:43:44:4c:41:42"; host.port=62000;
    host.isWiredCarPlaySimulator=YES;host.wiredIPv6Addresses=@[@"::1"];
    state[0xa0]=1;state[0x68]=1;
    *(void **)(state+0xa8)=(__bridge void *)host;
    *(CFStringRef *)(state+0x50)=CFSTR("en2");
    *(uint32_t *)(state+0x58)=16;*(double *)(state+0x48)=42;
    *(double *)(state+0x38)=40;
    *(double *)(state+0xb0)=1234;
    NSDictionary *map=@{@"en2":@[@"fe80::1"]};
    *(CFDictionaryRef *)(state+0x98)=(__bridge CFDictionaryRef)map;
    auto restored=[&]{assert(state[0x40]==0 && state[0x68]==1);
        assert(*(CFStringRef *)(state+0x50)==CFSTR("en2"));
        assert(*(uint32_t *)(state+0x58)==16 && *(double *)(state+0x48)==42);
        assert(*(CFDictionaryRef *)(state+0x98)==(__bridge CFDictionaryRef)map);};
    if(GuardedLayout) {
        // A matched image alone must not permit writes to incompatible live
        // state. FakeUpdate observes the untouched physical inputs on fallback.
        scoped=false;*(double *)(state+0x38)=0;
        assert(Update(helper)==-123);restored();
        *(double *)(state+0x38)=40;
        *(CFTypeRef *)(state+0x98)=(__bridge CFTypeRef)@[];
        assert(Update(helper)==-123);
        assert(state[0x40]==0 && state[0x68]==1 && *(uint32_t *)(state+0x58)==16);
        *(CFDictionaryRef *)(state+0x98)=(__bridge CFDictionaryRef)map;
        *(CFTypeRef *)(block+0x28)=helper;*(int32_t *)(block+0x40)=4;
        *(uint32_t *)(state+0xb8)=1;*(double *)(state+0x38)=0;
        CDV3AudioHost(helper,true);Event(block);assert(!*(void **)(state+0xa8) && !audioOwn);
        *(void **)(state+0xa8)=(__bridge void *)host;*(double *)(state+0x38)=40;
        assert(updates==2 && events==1);updates=0;events=0;
        puts("Guarded layout refusal preserves native forwarding");
    }
    scoped=true; assert(Update(helper)==-123); restored();
    throwUpdate=true; bool caught=false;
    @try {Update(helper);} @catch(NSException *e){(void)e;caught=true;}
    assert(caught);restored();throwUpdate=false;
    scoped=false;
    auto foreign=[HarnessHelper new];memcpy(foreign.storage.mutableBytes,state,0x200);
    auto foreignHost=[CARSessionRequestHost new];foreignHost.displayName=@"Another Car";
    *(void **)((uint8_t *)foreign.storage.mutableBytes+0xa8)=(__bridge void *)foreignHost;
    const auto audioBefore=audioCalls;Update((__bridge CFTypeRef)foreign);
    assert(audioOwn && audioCalls==audioBefore+1); // unrelated helper cannot cancel our device-audio lease
    *(uint32_t *)((uint8_t *)foreign.storage.mutableBytes+0xb8)=1;
    host.displayName=@"Another Car";Update(helper);restored();assert(!audioOwn);
    host.displayName=@"CarDash V3";host.port=62001;Update(helper);restored();
    host.port=62000;host.wiredIPv6Addresses=@[@"::2"];Update(helper);restored();
    host.wiredIPv6Addresses=@[@"::1"];state[0xa0]=0;Update(helper);restored();state[0xa0]=1;
    *(CFTypeRef *)(block+0x28)=helper;*(int32_t *)(block+0x40)=4;
    scoped=true;*(uint32_t *)(state+0xb8)=1;Event(block);
    assert(*(void **)(state+0xa8)==(__bridge void *)host && *(uint32_t *)(state+0xb8)==1);restored();
    scoped=false;host.displayName=@"Another Car";Event(block);assert(!*(void **)(state+0xa8));
    host.displayName=@"CarDash V3";*(void **)(state+0xa8)=(__bridge void *)host;
    scoped=true;cancelHost=true;*(uint32_t *)(state+0xb8)=1;Event(block);
    assert(!*(void **)(state+0xa8) && *(uint32_t *)(state+0xb8)==0);assert(!audioOwn);
    cancelHost=false;scoped=false;*(int32_t *)(block+0x40)=5;*(uint32_t *)(state+0xb8)=2;
    Event(block);assert(*(uint32_t *)(state+0xb8)==2);
    assert(updates==8 && events==4);
    puts("10 native lifecycle cases passed");
    // The callback owns the final native helper reference, as in the observed
    // APTransport block. No further original update sets the transport back.
    *(void **)(state+0xa8)=(__bridge void *)host;
    *(int32_t *)(block+0x40)=4;*(uint32_t *)(state+0xb8)=1;
    consumeHelper=true;Event(block);
    assert(helperDestroyed && updates==8 && events==5);
    puts("Final-reference callback lifetime case passed");
} }
