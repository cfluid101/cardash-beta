#import "Common.h"
@interface CDGateFixture:NSObject
- (void)setPort:(long long)value;
- (void)startSessionWithHost:(id)host completion:(void(^)(void))completion;
@end
@implementation CDGateFixture
- (void)setPort:(long long)value {(void)value;}
- (void)startSessionWithHost:(id)host completion:(void(^)(void))completion {(void)host;(void)completion;}
@end
int main(void){@autoreleasepool{
    BOOL tests[]={CDMethodMatches(CDGateFixture.class,@"setPort:","v",@[@"q"],NO,NO),
        !CDMethodMatches(CDGateFixture.class,@"setPort:","v",@[@"i"],NO,NO),
        !CDMethodMatches(CDGateFixture.class,@"missing", "v",@[],NO,NO),
        CDMethodMatches(CDGateFixture.class,@"startSessionWithHost:completion:","v",@[@"@",@"@?"],NO,NO),
        !CDMethodMatches(CDGateFixture.class,@"startSessionWithHost:completion:","v",@[@"@"],NO,NO),
        !CDMethodMatches(CDGateFixture.class,@"setPort:","v",@[@"q"],NO,YES),
        [CDConclusion(NO,NO,NO,NO) isEqual:@"request_withheld"],
        [CDConclusion(YES,NO,NO,NO) isEqual:@"request_issued_no_callback_or_transport"],
        [CDConclusion(YES,YES,NO,NO) isEqual:@"callback_observed_without_transport"],
        [CDConclusion(YES,YES,YES,NO) isEqual:@"loopback_reached_authentication_not_implemented"],
        [CDConclusion(YES,YES,YES,YES) isEqual:@"new_session_observed_not_live_video_verified"]};
    for(NSUInteger i=0;i<sizeof(tests)/sizeof(BOOL);i++)if(!tests[i]){fprintf(stderr,"Gate test %lu failed\n",(unsigned long)i);return 1;}
    puts("11 ABI/ownership/conclusion checks passed; no device calls");return 0;
}}
