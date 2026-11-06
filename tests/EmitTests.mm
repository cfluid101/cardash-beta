#import "Common.h"
#include <atomic>
#include <thread>
#include <vector>

int main(void) { @autoreleasepool {
    std::atomic<int> ready{0};std::atomic<bool> start{false};std::vector<std::thread> writers;
    for(int worker=0;worker<16;worker++)writers.emplace_back([&,worker]{@autoreleasepool{
        NSString *payload=[@"x" stringByPaddingToLength:65536 withString:@"x" startingAtIndex:0];
        ready.fetch_add(1);while(!start.load())std::this_thread::yield();
        for(int sequence=0;sequence<12;sequence++)CDEmit(@"parallel_emit",@{@"worker":@(worker),@"sequence":@(sequence),@"payload":payload});
    }});
    while(ready.load()!=16)std::this_thread::yield();start.store(true);
    for(auto &writer:writers)writer.join();return 0;
}}
