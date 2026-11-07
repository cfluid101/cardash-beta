#define CDV3_VIDEO_BUDGET_TEST 1
#include "../native/VideoBudget.mm"
#include <cassert>
#include <cstdio>
static uint32_t request=3000000;
static uint32_t BudgetRequested() {return request;}
static unsigned calls=0;
static CFDictionaryRef Original(uint8_t *) {++calls;return (CFDictionaryRef)CFRetain((__bridge CFDictionaryRef)@{@"Bandwidth":@25000000,@"Other":@7});}
static int32_t Property(CFTypeRef display,CFStringRef,CFAllocatorRef,CFTypeRef *out) {*out=CFRetain(display);return 0;}
static int64_t Read(CFDictionaryRef d) {int64_t value=0;assert(CFNumberGetValue((CFNumberRef)CFDictionaryGetValue(d,CFSTR("Bandwidth")),kCFNumberSInt64Type,&value));return value;}
int main() {@autoreleasepool {
 BudgetOriginal=Original;BudgetDisplayProperty=Property;BudgetUUIDKey=CFSTR("UUID");BudgetBandwidthKey=CFSTR("Bandwidth");
 alignas(16) uint8_t state[0x500]={};state[0x150]=state[0x152]=1;
 *(CFTypeRef *)(state+0x38)=CFSTR("b7e6c5a0-1111-4000-8000-000000000001");
 auto result=BudgetNetworkInfo(state);assert(Read(result)==3000000);assert(CFDictionaryContainsKey(result,CFSTR("Other")));CFRelease(result);
 *(CFTypeRef *)(state+0x38)=CFSTR("unrelated-display");result=BudgetNetworkInfo(state);assert(Read(result)==25000000);CFRelease(result);
 *(CFTypeRef *)(state+0x38)=CFSTR("b7e6c5a0-1111-4000-8000-000000000001");request=0;
 result=BudgetNetworkInfo(state);assert(Read(result)==25000000);CFRelease(result);
 request=3000000;state[0x150]=0;result=BudgetNetworkInfo(state);assert(Read(result)==25000000);CFRelease(result);
 assert(calls==4);puts("Video budget scope and native fallback passed");
}}
