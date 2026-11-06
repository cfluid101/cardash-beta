#import "Common.h"
#include <atomic>
#include <poll.h>
#include <spawn.h>
#include <signal.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <fcntl.h>
#include <unistd.h>
#include <mach-o/dyld.h>
#include <dlfcn.h>
#include <vector>
#include <string>
extern char **environ;
extern "C" int proc_pidpath(int,void *,uint32_t);
extern "C" int proc_listallpids(void *,int);

static std::atomic<bool> cancelled(false),exiting(false);
static NSObject *stateLock;
static BOOL running=NO;
static NSString *reportName=@"",*lastError=@"";
static void Terminate(int sig){(void)sig;cancelled=true;exiting=true;}
int CDPrepare(void){
    NSString *root=CDRoot();if(mkdir(root.fileSystemRepresentation,0750)&&errno!=EEXIST)return 1;
    int directory=open(root.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(directory<0)return 1;
    struct stat st;if(fstat(directory,&st)||st.st_uid!=getuid()||(st.st_mode&0022)){close(directory);return 1;}
    gid_t group=501;
#if CD_HOST_TEST
    group=getgid();
#endif
    if(fchown(directory,getuid(),group)||fchmod(directory,0750)){close(directory);return 1;}
    for(const char *name:{"installation.log","helper-bootstrap.log"}){
        int fd=openat(directory,name,O_WRONLY|O_APPEND|O_CREAT|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK,0640);
        if(fd<0){close(directory);return 1;}
        BOOL safe=fstat(fd,&st)==0&&S_ISREG(st.st_mode)&&st.st_nlink==1&&st.st_uid==getuid();
        if(!safe||fchown(fd,getuid(),group)||fchmod(fd,0640)){close(fd);close(directory);return 1;}close(fd);
    }
    close(directory);return 0;
}

class Report {
    int fd_;size_t bytes_=0;bool truncated_=false;
public:
    explicit Report(int fd):fd_(fd){}
    ~Report(){fsync(fd_);close(fd_);}
    void put(NSString *event,NSDictionary *fields,bool critical=false){
        NSMutableDictionary *row=[fields mutableCopy];row[@"event"]=event;row[@"wall_time"]=@([[NSDate date] timeIntervalSince1970]);
        NSData *data=CDJSON(row);
        if(!critical&&bytes_+data.length>5*1024*1024){if(!truncated_){truncated_=true;put(@"output_truncated",@{@"reason":@"combined log size cap"},true);}return;}
        if(!CDWrite(fd_,data)){cancelled=true;@synchronized(stateLock){lastError=@"Could not write complete report (check free space)";}}
        bytes_+=data.length;
    }
};
struct Child {pid_t pid=-1;int output=-1;NSMutableData *partial=nil;bool clipped=false;};
static Child Spawn(NSString *program,NSArray<NSString *> *args) {
    Child c;int pipes[2];if(pipe(pipes))return c;
    fcntl(pipes[0],F_SETFD,FD_CLOEXEC);fcntl(pipes[1],F_SETFD,FD_CLOEXEC);fcntl(pipes[0],F_SETFL,O_NONBLOCK);
    posix_spawn_file_actions_t actions;posix_spawn_file_actions_init(&actions);
    posix_spawn_file_actions_addopen(&actions,STDIN_FILENO,"/dev/null",O_RDONLY,0);
    posix_spawn_file_actions_adddup2(&actions,pipes[1],STDOUT_FILENO);posix_spawn_file_actions_adddup2(&actions,pipes[1],STDERR_FILENO);
    posix_spawn_file_actions_addclose(&actions,pipes[0]);posix_spawn_file_actions_addclose(&actions,pipes[1]);
    posix_spawnattr_t attr;posix_spawnattr_init(&attr);
    sigset_t mask,defaults;sigemptyset(&mask);sigemptyset(&defaults);for(int sig:{SIGTERM,SIGINT,SIGABRT,SIGPIPE})sigaddset(&defaults,sig);
    posix_spawnattr_setsigmask(&attr,&mask);posix_spawnattr_setsigdefault(&attr,&defaults);
    posix_spawnattr_setflags(&attr,POSIX_SPAWN_SETPGROUP|POSIX_SPAWN_SETSIGMASK|POSIX_SPAWN_SETSIGDEF);posix_spawnattr_setpgroup(&attr,0);
    std::vector<std::string> storage;storage.emplace_back(program.fileSystemRepresentation);for(NSString *a in args)storage.emplace_back(a.UTF8String);
    std::vector<char *> argv;for(auto &s:storage)argv.push_back(s.data());argv.push_back(nullptr);
    int err=posix_spawn(&c.pid,program.fileSystemRepresentation,&actions,&attr,argv.data(),environ);
    posix_spawnattr_destroy(&attr);posix_spawn_file_actions_destroy(&actions);close(pipes[1]);
    if(err){close(pipes[0]);c.pid=-1;errno=err;return c;}c.output=pipes[0];c.partial=[NSMutableData data];return c;
}
static void Drain(Child &child,Report &report,NSString *source) {
    if(child.output<0)return;char buffer[4096];
    // A noisy pipe must not starve deadlines or CANCEL. Work is bounded per poll.
    for(int pass=0;pass<16;pass++){
        ssize_t n=read(child.output,buffer,sizeof(buffer));if(n<=0)break;
        [child.partial appendBytes:buffer length:n];
        while(child.partial.length){
            const char *data=(const char *)child.partial.bytes;const char *end=(const char *)memchr(data,'\n',child.partial.length);
            size_t len=end?(size_t)(end-data):child.partial.length;
            if(!end&&len<16384)break;
            NSData *line=[child.partial subdataWithRange:NSMakeRange(0,MIN(len,(size_t)16384))];
            NSString *text=[[NSString alloc] initWithData:line encoding:NSUTF8StringEncoding]?:@"<non-UTF8 output omitted>";
            report.put(@"captured_output",@{@"source":source,@"text":text});
            if(!end&&!child.clipped){child.clipped=true;report.put(@"output_truncated",@{@"source":source,@"reason":@"line exceeded 16 KiB"},true);}
            [child.partial replaceBytesInRange:NSMakeRange(0,end?len+1:len) withBytes:NULL length:0];
        }
    }
}
static int Reap(Child &child,Report &report,NSString *source,BOOL terminate) {
    if(child.pid<=0)return 0;
    if(terminate)kill(-child.pid,SIGTERM);
    int status=0;double until=CDClock()+1.5;
    for(;;){pid_t got=waitpid(child.pid,&status,WNOHANG);if(got==child.pid)break;if(got<0&&errno!=EINTR)break;
        Drain(child,report,source);if(CDClock()>until){kill(-child.pid,SIGKILL);while(waitpid(child.pid,&status,0)<0&&errno==EINTR){}break;}usleep(10000);}
    Drain(child,report,source);
    if(child.partial.length){NSString *tail=[[NSString alloc] initWithData:child.partial encoding:NSUTF8StringEncoding]?:@"<non-UTF8 tail>";report.put(@"captured_output",@{@"source":source,@"text":tail,@"partial_line":@YES});}
    close(child.output);child.output=-1;child.pid=-1;return status;
}
static NSString *SelfPath(void){char p[4096];uint32_t n=sizeof(p);if(_NSGetExecutablePath(p,&n))return nil;char real[PATH_MAX];return realpath(p,real)?@(real):@(p);}
static NSArray *ServicePIDs(void){
    pid_t pids[2048];int count=proc_listallpids(pids,sizeof(pids));NSMutableArray *rows=[NSMutableArray array];
    for(int i=0;i<MIN(count,2048);i++){char path[4096]={0};if(proc_pidpath(pids[i],path,sizeof(path))<=0)continue;NSString *name=[@(path) lastPathComponent];
        if([@[@"carkitd",@"accessoryd",@"SpringBoard",@"backboardd"] containsObject:name])[rows addObject:@{@"name":name,@"pid":@(pids[i])}];}
    return rows;
}
static void RunSuite(int fd,NSString *name) {@autoreleasepool{
    Report log(fd);double started=CDClock();
    log.put(@"run_start",@{@"version":CD_VERSION,@"report":name,@"model":CDSystem("hw.machine"),@"build":CDSystem("kern.osversion"),@"uid":@(getuid()),@"deadline_seconds":@180,@"authentication_implemented":@NO,@"live_carplay_verified":@NO},true);
    log.put(@"service_processes_before",@{@"processes":ServicePIDs()},true);
    NSString *manifestPath=@"/var/jb/usr/share/cardash-diagnostics/manifest.json";
    int manifestFD=open(manifestPath.fileSystemRepresentation,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if(manifestFD>=0){char b[16384];ssize_t n=read(manifestFD,b,sizeof(b));close(manifestFD);if(n>0){id value=[NSJSONSerialization JSONObjectWithData:[NSData dataWithBytes:b length:n] options:0 error:NULL];if([value isKindOfClass:NSDictionary.class])log.put(@"installed_payload_manifest",value,true);}}
    NSString *install=[CDRoot() stringByAppendingPathComponent:@"installation.log"];
    int installFD=open(install.fileSystemRepresentation,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if(installFD>=0){char b[32768];ssize_t n=read(installFD,b,sizeof(b));close(installFD);if(n>0)log.put(@"installation_log",@{@"text":[[NSString alloc] initWithBytes:b length:n encoding:NSUTF8StringEncoding]?:@"<unreadable encoding>"});}
    Child system;NSString *logTool=nil;
#if !CD_HOST_TEST
    for(NSString *path in @[@"/usr/bin/log",@"/var/jb/usr/bin/log"])if(access(path.fileSystemRepresentation,X_OK)==0){logTool=path;break;}
#endif
    if(logTool)system=Spawn(logTool,@[@"stream",@"--style",@"ndjson",@"--level",@"debug",@"--predicate",@"process == 'carkitd' OR process == 'accessoryd' OR process == 'CarPlay' OR subsystem CONTAINS[c] 'CarPlay' OR subsystem CONTAINS[c] 'CarKit'"]);
    log.put(@"system_log_collector",@{@"started":@(system.pid>0),@"reason":system.pid>0?@"bounded process-filtered stream":@"log utility unavailable; native output and ASL fallback will still be recorded"},true);
    NSArray *profiles=@[@"inventory",@"displays",@"receiver",@"root-simulator-key",@"root-simulator-no-key",@"root-standard-key",@"mobile-simulator-key",@"displays",@"system-log-fallback",@"inventory"];
#if CD_HOST_TEST
    profiles=@[@"host-fixture",@"host-fixture-2"];
#endif
    NSUInteger completed=0;BOOL failed=NO;
    for(NSString *profile in profiles){
        if(cancelled||CDClock()-started>180){log.put(@"remaining_stages_withheld",@{@"reason":cancelled?@"cancelled":@"suite deadline"},true);break;}
        Child child=Spawn(SelfPath(),@[@"--worker",profile]);
        if(child.pid<0){log.put(@"spawn_failed",@{@"profile":profile,@"errno":@(errno)},true);failed=YES;break;}
        pid_t pid=child.pid;log.put(@"worker_start",@{@"profile":profile,@"pid":@(pid)},true);double began=CDClock();BOOL timedOut=NO;int status=0;
        double budget=[profile containsString:@"-key"]?25:15;
#if CD_HOST_TEST
        budget=.65;
#endif
        for(;;){
            Drain(child,log,profile);Drain(system,log,@"system_log");
            pid_t got=waitpid(pid,&status,WNOHANG);
            if(got==pid){Drain(child,log,profile);if(child.partial.length)log.put(@"captured_output",@{@"source":profile,@"text":[[NSString alloc] initWithData:child.partial encoding:NSUTF8StringEncoding]?:@"<partial non-UTF8 output>"});close(child.output);child.output=-1;child.pid=-1;break;}
            if(got<0&&errno!=EINTR){status=0;failed=YES;log.put(@"wait_failed",@{@"errno":@(errno)},true);break;}
            timedOut=CDClock()-began>budget||CDClock()-started>180;
            if(cancelled||timedOut){status=Reap(child,log,profile,YES);break;}
            usleep(10000);
        }
        int code=WIFEXITED(status)?WEXITSTATUS(status):-1,signal=WIFSIGNALED(status)?WTERMSIG(status):0;
        log.put(@"worker_exit",@{@"profile":profile,@"pid":@(pid),@"exit_code":@(code),@"signal":@(signal),@"timed_out":@(timedOut),@"cancelled":@(cancelled.load()),@"elapsed_seconds":@(CDClock()-began)},true);completed++;
        if(signal||timedOut||code!=0||failed){failed=YES;log.put(@"remaining_stages_withheld",@{@"reason":@"worker failed, timed out, unsupported target, or pre-existing session; no further active attempts"},true);break;}
    }
    if(system.pid>0){pid_t pid=system.pid;int status=Reap(system,log,@"system_log",YES);log.put(@"system_log_exit",@{@"pid":@(pid),@"status":@(status)},true);}
    log.put(@"service_processes_after",@{@"processes":ServicePIDs()},true);
    log.put(@"run_end",@{@"completed_workers":@(completed),@"cancelled":@(cancelled.load()),@"worker_failure":@(failed),@"elapsed_seconds":@(CDClock()-started),@"live_carplay_verified":@NO,@"note":@"Read per-stage native_summary records. A request/callback/socket is not proof of a live authenticated CarPlay display."},true);
    @synchronized(stateLock){running=NO;}
}}
static NSDictionary *Status(void){@synchronized(stateLock){return @{@"running":@(running),@"report":reportName,@"error":lastError,@"version":CD_VERSION};}}
static NSDictionary *Command(NSString *cmd){
    if([cmd isEqual:@"STATUS"])return Status();
    if([cmd isEqual:@"CANCEL"]){cancelled=true;return Status();}
    if(![cmd isEqual:@"RUN"])return @{@"error":@"unknown command"};
    @synchronized(stateLock){if(running)return Status();cancelled=false;lastError=@"";
        reportName=[NSString stringWithFormat:@"report-%.0f-%@.log",[[NSDate date] timeIntervalSince1970]*1000,NSUUID.UUID.UUIDString];
        NSString *path=[CDRoot() stringByAppendingPathComponent:reportName];
        int fd=open(path.fileSystemRepresentation,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0640);
        if(fd<0){lastError=[NSString stringWithFormat:@"Cannot create report (errno %d)",errno];return Status();}
#if !CD_HOST_TEST
        if(fchown(fd,0,501)){close(fd);lastError=@"Cannot set report ownership";return Status();}
#endif
        running=YES;NSString *name=[reportName copy];dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY,0),^{RunSuite(fd,name);});return Status();
    }
}
static BOOL PeerAllowed(int socketFD){
    uid_t uid;gid_t gid;if(getpeereid(socketFD,&uid,&gid))return NO;
#if CD_HOST_TEST
    return uid==getuid();
#else
    if(uid!=0&&uid!=501)return NO;
    pid_t pid=0;socklen_t size=sizeof(pid);if(getsockopt(socketFD,SOL_LOCAL,LOCAL_PEERPID,&pid,&size))return NO;
    char actual[4096]={0},expected[PATH_MAX]={0};if(proc_pidpath(pid,actual,sizeof(actual))<=0)return NO;
    NSString *path=uid==0?CD_HELPER:CD_APP;
    return realpath(path.fileSystemRepresentation,expected)&&strcmp(actual,expected)==0;
#endif
}
int CDDaemon(BOOL hostMode){@autoreleasepool{
    stateLock=[NSObject new];signal(SIGPIPE,SIG_IGN);signal(SIGTERM,Terminate);signal(SIGINT,Terminate);
    struct stat rootStat;NSString *root=CDRoot();
    if(lstat(root.fileSystemRepresentation,&rootStat)||!S_ISDIR(rootStat.st_mode)||rootStat.st_uid!=getuid()||(rootStat.st_mode&0022)){fprintf(stderr,"Unsafe or unavailable diagnostic directory\n");return 1;}
    int lock=open([[root stringByAppendingPathComponent:@"helper.lock"] fileSystemRepresentation],O_RDWR|O_CREAT|O_NOFOLLOW|O_CLOEXEC,0600);
    if(lock<0||flock(lock,LOCK_EX|LOCK_NB)){if(lock>=0)close(lock);return 1;}
    int listener=-1;
    if(hostMode){
        listener=socket(AF_UNIX,SOCK_STREAM,0);struct sockaddr_un address={};address.sun_family=AF_UNIX;
        NSString *path=[root stringByAppendingPathComponent:@"control.sock"];if(path.length>=sizeof(address.sun_path))return 1;strlcpy(address.sun_path,path.fileSystemRepresentation,sizeof(address.sun_path));
        if(bind(listener,(struct sockaddr *)&address,sizeof(address))||listen(listener,8))return 1;
    }else{
        typedef int (*Activate)(const char *,int **,size_t *);Activate activate=(Activate)dlsym(RTLD_DEFAULT,"launch_activate_socket");int *fds=NULL;size_t count=0;
        if(!activate||activate("ControlListeners",&fds,&count)||count!=1){fprintf(stderr,"launchd socket unavailable\n");free(fds);return 1;}listener=fds[0];free(fds);
    }
    fcntl(listener,F_SETFD,FD_CLOEXEC);double last=CDClock();
    while(!exiting){@autoreleasepool{
        struct pollfd ready={listener,POLLIN,0};int result=poll(&ready,1,100);
        if(result>0&&(ready.revents&POLLIN)){
            int client=accept(listener,NULL,NULL);if(client<0)continue;fcntl(client,F_SETFD,FD_CLOEXEC);
            struct timeval timeout={0,300000};setsockopt(client,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout));setsockopt(client,SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof(timeout));
            if(PeerAllowed(client)){
                char buffer[65]={0};size_t used=0;while(used<64){ssize_t n=read(client,buffer+used,64-used);if(n<=0)break;used+=n;if(memchr(buffer,'\n',used))break;}
                char *newline=(char *)memchr(buffer,'\n',used);NSDictionary *reply;
                if(!newline)reply=@{@"error":@"incomplete command"};else{*newline=0;NSString *command=@(buffer);reply=Command(command);}
                CDWrite(client,CDJSON(reply));last=CDClock();
            }else CDWrite(client,CDJSON(@{@"error":@"peer not authorized"}));close(client);
        }
        @synchronized(stateLock){if(!running&&CDClock()-last>30)break;}
    }}
    cancelled=true;for(;;){BOOL busy;@synchronized(stateLock){busy=running;}if(!busy)break;usleep(10000);}
    close(listener);close(lock);return 0;
}}
