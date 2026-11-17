// SPDX-License-Identifier: GPL-3.0-only
// Loopback-only RTCP timing endpoint for the SSH research transport.
#include <sys/socket.h>
#include <netinet/in.h>
#include <sys/time.h>
#include <fcntl.h>
#include <cstring>
struct Timing {
 int udp=-1,control=-1,connection=-1;unsigned peer=0,requests=0,replies=0;double last=0;
 static int bindPort(int type,int port){int fd=socket(AF_INET6,type,0);if(fd<0)return -1;int one=1;setsockopt(fd,IPPROTO_IPV6,IPV6_V6ONLY,&one,sizeof(one));sockaddr_in6 a={};a.sin6_family=AF_INET6;a.sin6_addr=in6addr_loopback;a.sin6_port=htons(port);if(bind(fd,(sockaddr*)&a,sizeof(a))||(type==SOCK_STREAM&&listen(fd,1))){close(fd);return -1;}fcntl(fd,F_SETFL,O_NONBLOCK);return fd;}
 bool start(){udp=bindPort(SOCK_DGRAM,62003);control=bindPort(SOCK_STREAM,62004);return udp>=0&&control>=0;}
 static void stamp(unsigned char *b){timeval t;gettimeofday(&t,nullptr);uint64_t v=((uint64_t(t.tv_sec)+2208988800ULL)<<32)|((uint64_t(t.tv_usec)<<32)/1000000);for(int i=7;i>=0;--i){b[i]=v&255;v>>=8;}}
 void step(){
  if(connection<0){connection=accept(control,nullptr,nullptr);if(connection>=0)fcntl(connection,F_SETFL,O_NONBLOCK);}
  if(connection>=0){unsigned char b[2];ssize_t n=recv(connection,b,2,MSG_PEEK);if(n==2){recv(connection,b,2,0);peer=(b[0]<<8)|b[1];close(connection);connection=-1;CDEmit(@"timing_peer",@{@"port":@(peer)});}else if(n==0){close(connection);connection=-1;}}
  sockaddr_in6 a={};socklen_t len=sizeof(a);unsigned char b[128];ssize_t n;
  while((n=recvfrom(udp,b,sizeof(b),0,(sockaddr*)&a,&len))>0){if(n!=32||!IN6_IS_ADDR_LOOPBACK(&a.sin6_addr))continue;if(b[1]==210){unsigned char out[32]={0x80,211,0,7};memcpy(out+8,b+24,8);stamp(out+16);stamp(out+24);sendto(udp,out,32,0,(sockaddr*)&a,len);requests++;}else if(b[1]==211)replies++;}
  if(peer&&CDClock()-last>.5){unsigned char b[32]={0x80,210,0,7};stamp(b+24);a={};a.sin6_family=AF_INET6;a.sin6_addr=in6addr_loopback;a.sin6_port=htons(peer);sendto(udp,b,32,0,(sockaddr*)&a,sizeof(a));last=CDClock();}
 }
 ~Timing(){if(udp>=0)close(udp);if(control>=0)close(control);if(connection>=0)close(connection);}
};
