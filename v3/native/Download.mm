#import <Foundation/Foundation.h>
#include <signal.h>
#include <unistd.h>
#include <sys/stat.h>
@interface Fetch:NSObject<NSURLSessionDownloadDelegate>
@property(nonatomic)BOOL done;
@property(nonatomic)int result;
@property(nonatomic,strong)NSString *output;
@property(nonatomic,strong)NSURLSession *session;
@end
@implementation Fetch
- (void)URLSession:(__unused NSURLSession *)s downloadTask:(NSURLSessionDownloadTask *)t didWriteData:(__unused int64_t)n totalBytesWritten:(int64_t)total totalBytesExpectedToWrite:(int64_t)expected {if(total>32*1024*1024||expected>32*1024*1024)[t cancel];}
- (void)URLSession:(__unused NSURLSession *)s downloadTask:(NSURLSessionDownloadTask *)t didFinishDownloadingToURL:(NSURL *)url {
 NSHTTPURLResponse *r=(NSHTTPURLResponse *)t.response;
 if(r.statusCode!=200){fprintf(stderr,"Download returned HTTP %ld\n",(long)r.statusCode);return;}
 NSError *error=nil;NSData *data=[NSData dataWithContentsOfURL:url options:NSDataReadingMappedIfSafe error:&error];
 if(!data||data.length>32*1024*1024||![data writeToFile:self.output options:NSDataWritingAtomic error:&error]){fprintf(stderr,"Download save failed: %s\n",error.localizedDescription.UTF8String?:"size limit");return;}
 chmod(self.output.fileSystemRepresentation,0600);self.result=0;
}
- (void)URLSession:(__unused NSURLSession *)s task:(__unused NSURLSessionTask *)t didCompleteWithError:(NSError *)error {
 if(error)fprintf(stderr,"Download failed: %s\n",error.localizedDescription.UTF8String);self.done=YES;
}
@end
static void deadline(int s){(void)s;_exit(124);}
int main(int argc,char **argv){@autoreleasepool{
 if(argc!=2)return 2;signal(SIGALRM,deadline);alarm(44);
 Fetch *f=[Fetch new];f.output=@(argv[1]);f.result=1;
 NSURLSessionConfiguration *cfg=[NSURLSessionConfiguration ephemeralSessionConfiguration];cfg.timeoutIntervalForRequest=15;cfg.timeoutIntervalForResource=40;
 f.session=[NSURLSession sessionWithConfiguration:cfg delegate:f delegateQueue:NSOperationQueue.mainQueue];
 NSMutableURLRequest *request=[NSMutableURLRequest requestWithURL:[NSURL URLWithString:@"https://github.com/shihabal3amri/DiPlay/releases/download/v0.2.22/DiPlay-0.2.22.apk"]];[request setValue:@"CarDash-V3-Native-Preview/3.0.0-beta.3" forHTTPHeaderField:@"User-Agent"];
 [[f.session downloadTaskWithRequest:request]resume];while(!f.done)CFRunLoopRunInMode(kCFRunLoopDefaultMode,.05,false);[f.session invalidateAndCancel];return f.result;
}}
