#import <UIKit/UIKit.h>
#import "Common.h"
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

static NSData *ReadBounded(NSString *path,NSUInteger maximum) {
    int fd=open(path.fileSystemRepresentation,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);if(fd<0)return nil;
    struct stat st;if(fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_size<0||(unsigned long long)st.st_size>maximum){close(fd);return nil;}
    NSMutableData *out=[NSMutableData data];char bytes[8192];ssize_t n;
    while((n=read(fd,bytes,sizeof(bytes)))>0){if(out.length+n>maximum){close(fd);return nil;}[out appendBytes:bytes length:n];}close(fd);return n<0?nil:out;
}
static BOOL ReportName(NSString *name){return [name isKindOfClass:NSString.class]&&[name hasPrefix:@"report-"]&&[name hasSuffix:@".log"]&&[name isEqual:name.lastPathComponent]&&name.length<128;}
@interface CDView:UIViewController
@property UILabel *status;
@property UITextView *details;
@property UIButton *runButton,*cancelButton,*shareButton;
@property NSTimer *timer;
@property BOOL polling,active,started,smokeWritten;
@property BOOL simulatedRetry;
@property BOOL failedRun,historicalSelection;
@property NSString *historicalReference;
@property NSUInteger runRequests;
@property NSString *report,*lastError;
@property NSString *lastExport;
@property NSMutableArray *events;
@end
@implementation CDView
- (UIButton *)button:(NSString *)title action:(SEL)selector {
    UIButton *b=[UIButton buttonWithType:UIButtonTypeSystem];[b setTitle:title forState:UIControlStateNormal];b.titleLabel.font=[UIFont preferredFontForTextStyle:UIFontTextStyleHeadline];b.layer.cornerRadius=13;b.backgroundColor=[UIColor secondarySystemBackgroundColor];[b.heightAnchor constraintGreaterThanOrEqualToConstant:50].active=YES;[b addTarget:self action:selector forControlEvents:UIControlEventTouchUpInside];return b;
}
- (void)viewDidLoad {
    [super viewDidLoad];self.view.backgroundColor=UIColor.systemBackgroundColor;self.events=[NSMutableArray array];self.report=@"";self.lastError=@"";
    [self event:@"app_ipc_environment" detail:CDIPCEnvironment()];
    UILabel *title=[UILabel new];title.text=@"CarPlay Diagnostics";title.font=[UIFont preferredFontForTextStyle:UIFontTextStyleLargeTitle];title.adjustsFontForContentSizeCategory=YES;title.numberOfLines=0;
    UILabel *intro=[UILabel new];intro.text=@"Run the complete diagnostic once, then share one log. Keep this app open and the phone unlocked for about 2–3 minutes. Disconnect any real CarPlay receiver first.";intro.font=[UIFont preferredFontForTextStyle:UIFontTextStyleBody];intro.numberOfLines=0;
#if CD_SIM_TEST
    intro.text=@"SIMULATOR UI TEST — generated diagnostic worker output only. This does not attempt a native CarPlay session.";
#endif
    self.status=[UILabel new];self.status.text=@"Checking diagnostic helper…";self.status.font=[UIFont preferredFontForTextStyle:UIFontTextStyleHeadline];self.status.numberOfLines=0;
    self.details=[UITextView new];self.details.editable=NO;self.details.font=[UIFont monospacedSystemFontOfSize:12 weight:UIFontWeightRegular];self.details.backgroundColor=UIColor.secondarySystemBackgroundColor;self.details.layer.cornerRadius=12;
    self.runButton=[self button:@"Run diagnostics" action:@selector(run)];self.cancelButton=[self button:@"Cancel test" action:@selector(cancel)];self.shareButton=[self button:@"Share diagnostic log" action:@selector(share)];
    UILabel *foot=[UILabel new];foot.text=@"Separate from CarDash. The log records request, callback, transport and cleanup separately. It may include CarKit service messages; nothing is uploaded automatically.";foot.font=[UIFont preferredFontForTextStyle:UIFontTextStyleFootnote];foot.textColor=UIColor.secondaryLabelColor;foot.numberOfLines=0;
    UIScrollView *scroll=[UIScrollView new];scroll.translatesAutoresizingMaskIntoConstraints=NO;[self.view addSubview:scroll];
    UIStackView *stack=[[UIStackView alloc] initWithArrangedSubviews:@[title,intro,self.status,self.details,self.runButton,self.cancelButton,self.shareButton,foot]];stack.axis=UILayoutConstraintAxisVertical;stack.spacing=12;stack.translatesAutoresizingMaskIntoConstraints=NO;[scroll addSubview:stack];
    UILayoutGuide *guide=self.view.safeAreaLayoutGuide,*content=scroll.contentLayoutGuide,*frame=scroll.frameLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[[scroll.topAnchor constraintEqualToAnchor:guide.topAnchor],[scroll.bottomAnchor constraintEqualToAnchor:guide.bottomAnchor],[scroll.leadingAnchor constraintEqualToAnchor:guide.leadingAnchor],[scroll.trailingAnchor constraintEqualToAnchor:guide.trailingAnchor],[stack.topAnchor constraintEqualToAnchor:content.topAnchor constant:12],[stack.bottomAnchor constraintEqualToAnchor:content.bottomAnchor constant:-12],[stack.leadingAnchor constraintEqualToAnchor:content.leadingAnchor constant:20],[stack.trailingAnchor constraintEqualToAnchor:content.trailingAnchor constant:-20],[stack.widthAnchor constraintEqualToAnchor:frame.widthAnchor constant:-40],[stack.heightAnchor constraintGreaterThanOrEqualToAnchor:frame.heightAnchor constant:-24],[self.details.heightAnchor constraintGreaterThanOrEqualToConstant:90]]];
    self.cancelButton.enabled=NO;[self refresh];self.timer=[NSTimer scheduledTimerWithTimeInterval:1 target:self selector:@selector(refresh) userInfo:nil repeats:YES];
#if CD_SIM_TEST
    if(getenv("CD_SIM_AUTORUN"))dispatch_after(dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC),dispatch_get_main_queue(),^{[self run];});
#endif
}
- (void)event:(NSString *)name detail:(id)detail {if(self.events.count>=100)[self.events removeObjectAtIndex:0];[self.events addObject:@{@"event":name,@"time":@([[NSDate date] timeIntervalSince1970]),@"detail":detail?:@""}];}
- (void)command:(NSString *)command {
    if(self.polling)return;self.polling=YES;self.runButton.enabled=NO;self.cancelButton.enabled=NO;
    if([command isEqual:@"RUN"])self.shareButton.enabled=NO;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY,0),^{NSDictionary *reply=CDCommand(command);dispatch_async(dispatch_get_main_queue(),^{self.polling=NO;[self consume:reply command:command];});});
}
- (void)refresh {[self command:@"STATUS"];}
- (void)run {if(self.polling||self.active)return;self.started=YES;self.runRequests++;self.historicalReference=self.report;self.report=@"";self.failedRun=NO;self.historicalSelection=NO;self.lastError=@"";[self event:@"user_run" detail:CD_VERSION];[self command:@"RUN"];}
- (void)cancel {if(self.polling)return;[self event:@"user_cancel" detail:nil];[self command:@"CANCEL"];}
- (void)consume:(NSDictionary *)reply command:(NSString *)command {
    NSString *error=[reply[@"error"] isKindOfClass:NSString.class]?reply[@"error"]:@"";
    if([command isEqual:@"RUN"])self.failedRun=error.length>0;
    if(self.failedRun&&![command isEqual:@"RUN"]&&self.lastError.length)error=self.lastError;
    self.active=[reply[@"running"] boolValue];NSString *candidate=reply[@"report"];
    if(!self.failedRun&&!error.length&&ReportName(candidate)){self.report=candidate;self.historicalSelection=NO;}
    if(error.length&&![error isEqual:self.lastError])[self event:@"helper_error" detail:reply];self.lastError=error;
    if(!self.report.length&&!error.length&&!self.failedRun){NSArray *names=[[NSFileManager defaultManager] contentsOfDirectoryAtPath:CDRoot() error:NULL];for(NSString *name in [names sortedArrayUsingSelector:@selector(compare:)])if(ReportName(name)){self.report=name;self.historicalSelection=YES;}}
    UIApplication.sharedApplication.idleTimerDisabled=self.active;self.runButton.enabled=!self.active;self.cancelButton.enabled=self.active;self.shareButton.enabled=!self.active;
    self.status.text=error.length?@"Helper error — Share diagnostic log":self.active?@"Recording diagnostics…":self.report.length?(self.historicalSelection?@"Previous report — Share diagnostic log":@"Report ready — Share diagnostic log"):@"Ready to run";
    NSData *data=self.report.length?ReadBounded([CDRoot() stringByAppendingPathComponent:self.report],7*1024*1024):nil;
    NSString *text=data?[[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding]:@"";
    if(text.length>14000)text=[text substringFromIndex:text.length-14000];self.details.text=error.length?error:text.length?text:@"Version 0.1.2\nNo test starts during installation.\nEach run creates a new log.\nAuthentication and live-video capture are not implemented by this diagnostic.";
    if(self.details.text.length)[self.details scrollRangeToVisible:NSMakeRange(self.details.text.length-1,1)];
#if CD_SIM_TEST
    if(getenv("CD_SIM_FAIL_SECOND")&&!self.simulatedRetry&&!self.active&&[[NSFileManager defaultManager] fileExistsAtPath:[CDRoot() stringByAppendingPathComponent:@"simulate-failed-run"]]){self.simulatedRetry=YES;self.smokeWritten=NO;dispatch_async(dispatch_get_main_queue(),^{[self run];});return;}
    if(self.started&&!self.active&&(self.report.length||error.length)&&!self.smokeWritten){self.smokeWritten=YES;NSString *documents=NSSearchPathForDirectoriesInDomains(NSDocumentDirectory,NSUserDomainMask,YES).firstObject;
        if(getenv("CD_SIM_AUTOEXPORT"))[self share];
        [CDJSON(@{@"report":self.report,@"report_bytes":@(data.length),@"ui_status":self.status.text,@"helper_error":error,@"export":self.lastExport?:@"",@"run_requests":@(self.runRequests),@"native_carplay_attempted":@NO}) writeToFile:[documents stringByAppendingPathComponent:@"smoke.json"] atomically:YES];}
#endif
}
- (void)share {
    if(self.active)return;
    NSMutableData *exportData=[NSMutableData dataWithData:CDJSON(@{@"event":@"app_export",@"version":CD_VERSION,@"time":@([[NSDate date] timeIntervalSince1970]),@"report":self.report?:@"",@"report_scope":self.historicalSelection?@"historical":self.report.length?@"current":@"no_current_report",@"excluded_previous_report":self.failedRun?(self.historicalReference?:@""):@"",@"helper_error":self.lastError?:@"",@"live_carplay_verified":@NO})];
    for(NSDictionary *event in self.events)[exportData appendData:CDJSON(event)];
    NSData *report=ReportName(self.report)?ReadBounded([CDRoot() stringByAppendingPathComponent:self.report],7*1024*1024):nil;
    if(report){[exportData appendData:report];if(report.length&&((const char *)report.bytes)[report.length-1]!='\n')[exportData appendBytes:"\n" length:1];}
    // Supporting diagnostics are always current, even if a previous report is
    // readable or the most recent helper request failed.
    for(NSString *name in @[@"installation.log",@"helper-bootstrap.log"]){NSData *install=ReadBounded([CDRoot() stringByAppendingPathComponent:name],128*1024);NSString *text=install?[[NSString alloc] initWithData:install encoding:NSUTF8StringEncoding]:@"Log unavailable or exceeds 128 KiB";[exportData appendData:CDJSON(@{@"event":@"supporting_log",@"file":name,@"text":text?:@"unreadable encoding"})];}
    NSString *path=[NSTemporaryDirectory() stringByAppendingPathComponent:[NSString stringWithFormat:@"CarDash-Diagnostics-%@.log",NSUUID.UUID.UUIDString]];
    NSError *error=nil;if(![exportData writeToFile:path options:NSDataWritingAtomic error:&error]){self.status.text=[NSString stringWithFormat:@"Export failed: %@",error.localizedDescription];return;}
    [[NSFileManager defaultManager] setAttributes:@{NSFilePosixPermissions:@0600} ofItemAtPath:path error:NULL];
    self.lastExport=path;
    UIActivityViewController *share=[[UIActivityViewController alloc] initWithActivityItems:@[[NSURL fileURLWithPath:path]] applicationActivities:nil];share.popoverPresentationController.sourceView=self.shareButton;share.popoverPresentationController.sourceRect=self.shareButton.bounds;[self presentViewController:share animated:YES completion:nil];
}
@end
@interface CDApp:UIResponder<UIApplicationDelegate>
@property(nonatomic,strong) UIWindow *window;
@end
@implementation CDApp
- (BOOL)application:(UIApplication *)app didFinishLaunchingWithOptions:(NSDictionary *)options {(void)app;(void)options;self.window=[[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];self.window.rootViewController=[CDView new];[self.window makeKeyAndVisible];return YES;}
- (void)applicationDidEnterBackground:(UIApplication *)app {app.idleTimerDisabled=NO;}
@end
int main(int argc,char **argv){@autoreleasepool{return UIApplicationMain(argc,argv,nil,NSStringFromClass(CDApp.class));}}
