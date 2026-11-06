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
    UILabel *title=[UILabel new];title.text=@"CarPlay Diagnostics";title.font=[UIFont preferredFontForTextStyle:UIFontTextStyleLargeTitle];title.adjustsFontForContentSizeCategory=YES;title.numberOfLines=0;
    UILabel *intro=[UILabel new];intro.text=@"Run the complete diagnostic once, then share one log. Keep this app open and the phone unlocked for about 2–3 minutes. Disconnect any real CarPlay receiver first.";intro.font=[UIFont preferredFontForTextStyle:UIFontTextStyleBody];intro.numberOfLines=0;
#if CD_SIM_TEST
    intro.text=@"SIMULATOR UI TEST — generated diagnostic worker output only. This does not attempt a native CarPlay session.";
#endif
    self.status=[UILabel new];self.status.text=@"Checking diagnostic helper…";self.status.font=[UIFont preferredFontForTextStyle:UIFontTextStyleHeadline];self.status.numberOfLines=0;
    self.details=[UITextView new];self.details.editable=NO;self.details.font=[UIFont monospacedSystemFontOfSize:12 weight:UIFontWeightRegular];self.details.backgroundColor=UIColor.secondarySystemBackgroundColor;self.details.layer.cornerRadius=12;
    self.runButton=[self button:@"Run diagnostics" action:@selector(run)];self.cancelButton=[self button:@"Cancel test" action:@selector(cancel)];self.shareButton=[self button:@"Share diagnostic log" action:@selector(share)];
    UILabel *foot=[UILabel new];foot.text=@"Separate from CarDash. The log records request, callback, transport and cleanup separately. It may include CarKit service messages; nothing is uploaded automatically.";foot.font=[UIFont preferredFontForTextStyle:UIFontTextStyleFootnote];foot.textColor=UIColor.secondaryLabelColor;foot.numberOfLines=0;
    UIStackView *stack=[[UIStackView alloc] initWithArrangedSubviews:@[title,intro,self.status,self.details,self.runButton,self.cancelButton,self.shareButton,foot]];stack.axis=UILayoutConstraintAxisVertical;stack.spacing=12;stack.translatesAutoresizingMaskIntoConstraints=NO;[self.view addSubview:stack];
    UILayoutGuide *guide=self.view.safeAreaLayoutGuide;[NSLayoutConstraint activateConstraints:@[[stack.topAnchor constraintEqualToAnchor:guide.topAnchor constant:12],[stack.bottomAnchor constraintEqualToAnchor:guide.bottomAnchor constant:-12],[stack.leadingAnchor constraintEqualToAnchor:guide.leadingAnchor constant:20],[stack.trailingAnchor constraintEqualToAnchor:guide.trailingAnchor constant:-20],[self.details.heightAnchor constraintGreaterThanOrEqualToConstant:90]]];
    self.cancelButton.enabled=NO;[self refresh];self.timer=[NSTimer scheduledTimerWithTimeInterval:1 target:self selector:@selector(refresh) userInfo:nil repeats:YES];
#if CD_SIM_TEST
    if(getenv("CD_SIM_AUTORUN"))dispatch_after(dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC),dispatch_get_main_queue(),^{[self run];});
#endif
}
- (void)event:(NSString *)name detail:(id)detail {if(self.events.count>=100)[self.events removeObjectAtIndex:0];[self.events addObject:@{@"event":name,@"time":@([[NSDate date] timeIntervalSince1970]),@"detail":detail?:@""}];}
- (void)command:(NSString *)command {
    if(self.polling)return;self.polling=YES;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY,0),^{NSDictionary *reply=CDCommand(command);dispatch_async(dispatch_get_main_queue(),^{self.polling=NO;[self consume:reply];});});
}
- (void)refresh {[self command:@"STATUS"];}
- (void)run {if(self.polling||self.active)return;self.started=YES;[self event:@"user_run" detail:CD_VERSION];[self command:@"RUN"];}
- (void)cancel {if(self.polling)return;[self event:@"user_cancel" detail:nil];[self command:@"CANCEL"];}
- (void)consume:(NSDictionary *)reply {
    self.active=[reply[@"running"] boolValue];NSString *candidate=reply[@"report"];if(ReportName(candidate))self.report=candidate;
    NSString *error=[reply[@"error"] isKindOfClass:NSString.class]?reply[@"error"]:@"";
    if(error.length&&![error isEqual:self.lastError])[self event:@"helper_error" detail:reply];self.lastError=error;
    if(!self.report.length){NSArray *names=[[NSFileManager defaultManager] contentsOfDirectoryAtPath:CDRoot() error:NULL];for(NSString *name in [names sortedArrayUsingSelector:@selector(compare:)])if(ReportName(name))self.report=name;}
    UIApplication.sharedApplication.idleTimerDisabled=self.active;self.runButton.enabled=!self.active;self.cancelButton.enabled=self.active;self.shareButton.enabled=!self.active;
    self.status.text=error.length?@"Helper unavailable — Share diagnostic log":self.active?@"Recording diagnostics…":self.report.length?@"Report ready — Share diagnostic log":@"Ready to run";
    NSData *data=self.report.length?ReadBounded([CDRoot() stringByAppendingPathComponent:self.report],7*1024*1024):nil;
    NSString *text=data?[[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding]:@"";
    if(text.length>14000)text=[text substringFromIndex:text.length-14000];self.details.text=error.length?error:text.length?text:@"Version 0.1.0\nNo test starts during installation.\nEach run creates a new log.\nAuthentication and live-video capture are not implemented by this diagnostic.";
    if(self.details.text.length)[self.details scrollRangeToVisible:NSMakeRange(self.details.text.length-1,1)];
#if CD_SIM_TEST
    if(self.started&&!self.active&&self.report.length&&!self.smokeWritten){self.smokeWritten=YES;NSString *documents=NSSearchPathForDirectoriesInDomains(NSDocumentDirectory,NSUserDomainMask,YES).firstObject;
        if(getenv("CD_SIM_AUTOEXPORT"))[self share];
        [CDJSON(@{@"report":self.report,@"report_bytes":@(data.length),@"ui_status":self.status.text,@"helper_error":error,@"export":self.lastExport?:@"",@"native_carplay_attempted":@NO}) writeToFile:[documents stringByAppendingPathComponent:@"smoke.json"] atomically:YES];}
#endif
}
- (void)share {
    if(self.active)return;
    NSMutableData *exportData=[NSMutableData dataWithData:CDJSON(@{@"event":@"app_export",@"version":CD_VERSION,@"time":@([[NSDate date] timeIntervalSince1970]),@"report":self.report?:@"",@"helper_error":self.lastError?:@"",@"live_carplay_verified":@NO})];
    for(NSDictionary *event in self.events)[exportData appendData:CDJSON(event)];
    NSData *report=ReportName(self.report)?ReadBounded([CDRoot() stringByAppendingPathComponent:self.report],7*1024*1024):nil;
    if(report)[exportData appendData:report];else{for(NSString *name in @[@"installation.log",@"helper-bootstrap.log"]){NSData *install=ReadBounded([CDRoot() stringByAppendingPathComponent:name],128*1024);NSString *text=install?[[NSString alloc] initWithData:install encoding:NSUTF8StringEncoding]:@"Log unavailable";[exportData appendData:CDJSON(@{@"event":@"installation_fallback",@"file":name,@"text":text?:@"unreadable encoding"})];}}
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
