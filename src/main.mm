#import "Common.h"
#include <unistd.h>
#include <grp.h>
#include <signal.h>
int main(int argc,char **argv){
    if((argc==3&&!strcmp(argv[1],"--worker"))||(argc==2&&!strcmp(argv[1],"--log-worker"))){
        unsigned seconds=argc==2?185:30;
#if CD_HOST_TEST
        seconds=2;
#endif
        if(!CDInstallWorkerGuard(seconds))return 2;
    }
    if(argc==3&&!strcmp(argv[1],"--worker")&&!strcmp(argv[2],"mobile-simulator-key")){
#if !CD_HOST_TEST
        if(setgroups(0,NULL)||setgid(501)||setuid(501)||geteuid()!=501){fprintf(stderr,"Cannot drop worker identity\n");return 1;}
#endif
    }
    @autoreleasepool{
        if(argc==2&&!strcmp(argv[1],"--log-worker"))return CDLogWorker();
        if(argc==2&&!strcmp(argv[1],"--prepare")){
#if !CD_HOST_TEST
            if(geteuid()!=0)return 1;
#endif
            return CDPrepare();
        }
        if(argc==3&&!strcmp(argv[1],"--worker"))return CDWorker(@(argv[2]));
#if CD_HOST_TEST
        if(argc==2&&!strcmp(argv[1],"--host-daemon"))return CDDaemon(YES);
#endif
        if(argc==2&&!strcmp(argv[1],"--daemon")){if(geteuid()!=0)return 1;return CDDaemon(NO);}
        if(argc==2&&(!strcmp(argv[1],"--run")||!strcmp(argv[1],"--status")||!strcmp(argv[1],"--cancel"))){
            NSString *command=!strcmp(argv[1],"--run")?@"RUN":!strcmp(argv[1],"--status")?@"STATUS":@"CANCEL";
            NSDictionary *reply=CDCommand(command);CDWrite(STDOUT_FILENO,CDJSON(reply));return [reply[@"error"] length]?1:0;
        }
        fprintf(stderr,"Usage: cardash-diagnostics --run | --status | --cancel\n");return 2;
    }
}
