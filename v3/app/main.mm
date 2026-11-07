#import <UIKit/UIKit.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <ifaddrs.h>
#include <arpa/inet.h>
#include <unistd.h>

static NSDictionary *Request(NSString *action){
 int fd=socket(AF_UNIX,SOCK_STREAM,0);if(fd<0)return @{ @"ok":@NO,@"error":@"Could not open local service connection."};
 timeval timeout={15,0};setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout));setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof(timeout));
 int one=1;setsockopt(fd,SOL_SOCKET,SO_NOSIGPIPE,&one,sizeof(one));sockaddr_un addr={};addr.sun_family=AF_UNIX;strlcpy(addr.sun_path,"/var/jb/var/lib/cardash-v3/control.sock",sizeof(addr.sun_path));
 if(connect(fd,(sockaddr*)&addr,sizeof(addr))){close(fd);return @{ @"ok":@NO,@"error":@"V3 service is unavailable. Reinstall the V3 package and export the installation log if it persists."};}
 NSData *json=[NSJSONSerialization dataWithJSONObject:@{@"action":action} options:0 error:nil];NSMutableData *wire=[json mutableCopy];[wire appendBytes:"\n" length:1];NSUInteger sent=0;
 while(sent<wire.length){ssize_t n=send(fd,(const char *)wire.bytes+sent,wire.length-sent,0);if(n<=0)break;sent+=(NSUInteger)n;}
 NSMutableData *received=[NSMutableData data];char buf[8192];
 while(received.length<5*1024*1024){ssize_t n=recv(fd,buf,sizeof(buf),0);if(n<=0)break;[received appendBytes:buf length:(NSUInteger)n];if(buf[n-1]=='\n')break;}
 close(fd);id value=[NSJSONSerialization JSONObjectWithData:received options:0 error:nil];return [value isKindOfClass:NSDictionary.class]?value:@{@"ok":@NO,@"error":@"The V3 service did not return a complete response. Try again."};
}
static NSString *Addresses(){
 NSMutableOrderedSet *addresses=[NSMutableOrderedSet orderedSet];struct ifaddrs *all=NULL;
 if(getifaddrs(&all)==0){for(struct ifaddrs *p=all;p;p=p->ifa_next){if(!p->ifa_addr||p->ifa_addr->sa_family!=AF_INET)continue;NSString *name=@(p->ifa_name);if(![name hasPrefix:@"en"]&&![name hasPrefix:@"bridge"]&&![name hasPrefix:@"ap"])continue;char ip[INET_ADDRSTRLEN];if(inet_ntop(AF_INET,&((sockaddr_in*)p->ifa_addr)->sin_addr,ip,sizeof(ip)))[addresses addObject:[NSString stringWithFormat:@"http://%s:8890",ip]];}freeifaddrs(all);}
 if(!addresses.count)return @"Enable Personal Hotspot, then connect the car to it.\nUsual hotspot address: http://172.20.10.1:8890";
 return [addresses.array componentsJoinedByString:@"\n"];
}
@interface Controller:UIViewController<UIDocumentPickerDelegate>
@property(nonatomic,strong) UILabel *status;
@property(nonatomic,strong) UILabel *addresses;
@property(nonatomic,strong) UIButton *prepare;
@property(nonatomic,strong) UIButton *start;
@property(nonatomic,strong) UIButton *stop;
@property(nonatomic,strong) NSTimer *timer;
@property(nonatomic) BOOL polling;
@end
@implementation Controller
- (UIButton *)button:(NSString *)title action:(SEL)action {
 UIButton *b=[UIButton buttonWithType:UIButtonTypeSystem];[b setTitle:title forState:UIControlStateNormal];b.titleLabel.font=[UIFont systemFontOfSize:17 weight:UIFontWeightSemibold];b.backgroundColor=[UIColor colorWithRed:.12 green:.23 blue:.36 alpha:1];b.layer.cornerRadius=12;[b setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];[b.heightAnchor constraintEqualToConstant:48].active=YES;[b addTarget:self action:action forControlEvents:UIControlEventTouchUpInside];return b;
}
- (UILabel *)label:(NSString *)text size:(CGFloat)size {
 UILabel *l=[UILabel new];l.text=text;l.font=[UIFont systemFontOfSize:size];l.textColor=UIColor.whiteColor;l.numberOfLines=0;return l;
}
- (void)viewDidLoad {
 [super viewDidLoad];self.view.backgroundColor=[UIColor colorWithRed:.035 green:.055 blue:.09 alpha:1];UIApplication.sharedApplication.idleTimerDisabled=YES;
 UIScrollView *scroll=[UIScrollView new];scroll.translatesAutoresizingMaskIntoConstraints=NO;[self.view addSubview:scroll];
 UIStackView *stack=[[UIStackView alloc]init];stack.axis=UILayoutConstraintAxisVertical;stack.spacing=14;stack.translatesAutoresizingMaskIntoConstraints=NO;[scroll addSubview:stack];
 [NSLayoutConstraint activateConstraints:@[[scroll.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],[scroll.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],[scroll.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor],[scroll.bottomAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.bottomAnchor],[stack.leadingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.leadingAnchor constant:24],[stack.trailingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.trailingAnchor constant:-24],[stack.topAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.topAnchor constant:24],[stack.bottomAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.bottomAnchor constant:-24],[stack.widthAnchor constraintEqualToAnchor:scroll.frameLayoutGuide.widthAnchor constant:-48]]];
 UILabel *title=[self label:@"CarDash V3" size:32];title.font=[UIFont systemFontOfSize:32 weight:UIFontWeightBold];[stack addArrangedSubview:title];
 [stack addArrangedSubview:[self label:@"Native CarPlay · 3.0.0 beta 5" size:17]];
 [stack addArrangedSubview:[self label:@"Native CarPlay video, touch and music/navigation audio. Sessions continue while connected. Microphone input, calls and Siri voice input are not supported in this beta." size:15]];
 self.status=[self label:@"Connecting to the V3 service…" size:16];[stack addArrangedSubview:self.status];
 self.prepare=[self button:@"Prepare CarPlay" action:@selector(prepareTapped)];[stack addArrangedSubview:self.prepare];
 [stack addArrangedSubview:[self button:@"Import downloaded DiPlay APK" action:@selector(importTapped)]];
 self.start=[self button:@"Start CarPlay" action:@selector(startTapped)];[stack addArrangedSubview:self.start];
 self.stop=[self button:@"Stop CarPlay" action:@selector(stopTapped)];[stack addArrangedSubview:self.stop];
 [stack addArrangedSubview:[self label:@"Connect the Tesla to Personal Hotspot, then open its address below and tap Start in the browser:" size:15]];
 self.addresses=[self label:@"Checking Tesla address…" size:16];self.addresses.textColor=[UIColor colorWithRed:.45 green:.78 blue:1 alpha:1];[stack addArrangedSubview:self.addresses];
 [stack addArrangedSubview:[self button:@"Open local preview in Safari" action:@selector(safariTapped)]];
 [stack addArrangedSubview:[self button:@"Export diagnostic report" action:@selector(exportTapped)]];
 [stack addArrangedSubview:[self label:@"First setup downloads and checks the public DiPlay 0.2.22 experimental accessory identity (about 18 MB). It is not Apple certification. No setup code is required. Use a trusted hotspot: connected devices can control the preview." size:13]];
 [stack addArrangedSubview:[self label:@"Keep the phone unlocked for your first test. This beta is limited to iPhone 8 Plus, iOS 16.6 build 20G75, with a rootless jailbreak. Installed CarBridge may affect which apps appear. Your original CarDash app and settings remain separate. Reports stay on this phone until you choose to share them; video is not recorded by this release." size:13]];
 self.timer=[NSTimer scheduledTimerWithTimeInterval:2 target:self selector:@selector(refresh) userInfo:nil repeats:YES];[self refresh];
}
- (void)show:(NSDictionary *)s {
 if(![s[@"ok"] boolValue]){self.status.text=s[@"error"]?:@"Service unavailable";return;}
 BOOL active=[s[@"active"] boolValue],ready=[s[@"identityReady"] boolValue],preparing=[s[@"preparing"] boolValue];
 self.prepare.enabled=!preparing&&!ready;self.start.enabled=ready&&!active&&!preparing;self.stop.enabled=active;
 [self.prepare setTitle:ready?@"Setup complete":preparing?@"Preparing…":@"Prepare CarPlay" forState:UIControlStateNormal];
 NSString *error=s[@"error"];
 if(error.length)self.status.text=error;
 else if(preparing)self.status.text=@"Preparing the experimental identity…";
 else if(active){NSDictionary *native=s[@"native"];NSString *phase=![native[@"authenticated"] boolValue]||![native[@"activated"] boolValue]?@"Starting native session":[s[@"nativeFrames"] unsignedLongLongValue]?@"Receiving native video":@"Waiting for native video";self.status.text=[NSString stringWithFormat:@"%@ · %@ seconds\n%@ video frames received",phase,s[@"sessionSeconds"],s[@"nativeFrames"]];}
 else self.status.text=ready?@"Setup complete. Tap Start in the Tesla browser to launch CarPlay. Audio stays on the phone or Bluetooth by default.":@"Tap Prepare CarPlay once to complete setup.";
 NSDictionary *network=s[@"network"];
 NSString *tesla=[network[@"ready"] boolValue]?network[@"url"]:[NSString stringWithFormat:@"Tesla address unavailable: %@",network[@"error"]?:@"checking…"];
 self.addresses.text=[NSString stringWithFormat:@"Tesla browser:\n%@\n\nOther browsers on this network:\n%@",tesla,Addresses()];
}
- (void)perform:(NSString *)action {
 if(self.polling)return;self.polling=YES;
 dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{@autoreleasepool{NSDictionary *s=Request(action);dispatch_async(dispatch_get_main_queue(),^{self.polling=NO;[self show:s];});}});
}
- (void)refresh {[self perform:@"status"];}
- (void)prepareTapped {
 UIAlertController *a=[UIAlertController alertControllerWithTitle:@"Prepare CarPlay" message:@"Download the verified public DiPlay experimental identity for this test? This uses about 18 MB and does not provide MFi certification." preferredStyle:UIAlertControllerStyleAlert];
 [a addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
 [a addAction:[UIAlertAction actionWithTitle:@"Prepare" style:UIAlertActionStyleDefault handler:^(__unused UIAlertAction *x){[self perform:@"prepare"];}]];[self presentViewController:a animated:YES completion:nil];
}
- (void)startTapped {[self perform:@"start"];}
- (void)importTapped {
 UIDocumentPickerViewController *picker=[[UIDocumentPickerViewController alloc]initWithDocumentTypes:@[@"public.data"] inMode:UIDocumentPickerModeImport];picker.delegate=self;[self presentViewController:picker animated:YES completion:nil];
}
- (void)documentPicker:(__unused UIDocumentPickerViewController *)picker didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls {
 NSURL *url=urls.firstObject;if(!url)return;
 dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{@autoreleasepool{
 BOOL scoped=[url startAccessingSecurityScopedResource];NSNumber *size=nil;NSError *error=nil;[url getResourceValue:&size forKey:NSURLFileSizeKey error:&error];NSDictionary *result;
 if(!size||size.unsignedLongLongValue>32*1024*1024)result=@{@"ok":@NO,@"error":@"Choose the official DiPlay 0.2.22 APK (under 32 MB)."};
 else {
  NSData *data=[NSData dataWithContentsOfURL:url options:NSDataReadingMappedIfSafe error:&error];NSString *folder=@"/var/mobile/Library/Caches/com.cfluid.cardash.v3";
  [[NSFileManager defaultManager]createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:@{NSFilePosixPermissions:@0700} error:&error];
  if(data&&[data writeToFile:[folder stringByAppendingPathComponent:@"identity-import.apk"] options:NSDataWritingAtomic error:&error])result=Request(@"import");
  else result=@{@"ok":@NO,@"error":error.localizedDescription?:@"Could not read the selected APK."};
 }
 if(scoped)[url stopAccessingSecurityScopedResource];dispatch_async(dispatch_get_main_queue(),^{[self show:result];});
 }});
}
- (void)stopTapped {[self perform:@"stop"];}
- (void)safariTapped {[UIApplication.sharedApplication openURL:[NSURL URLWithString:@"http://127.0.0.1:8890/"] options:@{} completionHandler:nil];}
- (void)exportTapped {
 dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{@autoreleasepool{NSDictionary *s=Request(@"report");NSString *report=s[@"report"];
 dispatch_async(dispatch_get_main_queue(),^{if(!report){[self show:s];return;}NSString *folder=@"/var/mobile/Library/Caches/com.cfluid.cardash.v3";[[NSFileManager defaultManager]createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:@{NSFilePosixPermissions:@0700} error:nil];NSURL *url=[NSURL fileURLWithPath:[folder stringByAppendingPathComponent:@"CarDash-V3-diagnostic.ndjson"]];NSError *error=nil;
 if(![report writeToURL:url atomically:YES encoding:NSUTF8StringEncoding error:&error]){self.status.text=error.localizedDescription;return;}
 UIActivityViewController *share=[[UIActivityViewController alloc]initWithActivityItems:@[url] applicationActivities:nil];share.popoverPresentationController.sourceView=self.view;[self presentViewController:share animated:YES completion:nil];});}});
}
@end
@interface Delegate:UIResponder<UIApplicationDelegate>
@property(nonatomic,strong)UIWindow *window;
@end
@implementation Delegate
- (BOOL)application:(__unused UIApplication *)app didFinishLaunchingWithOptions:(__unused NSDictionary *)options {self.window=[[UIWindow alloc]initWithFrame:UIScreen.mainScreen.bounds];self.window.rootViewController=[Controller new];[self.window makeKeyAndVisible];return YES;}
@end
int main(int argc,char **argv){@autoreleasepool{return UIApplicationMain(argc,argv,nil,NSStringFromClass(Delegate.class));}}
