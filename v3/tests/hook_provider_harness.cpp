// SPDX-License-Identifier: GPL-3.0-only
#include "../native/HookProvider.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
static void Hook(void *,void *,void **) {}
static void Other(void *,void *,void **) {}
int main() {
    std::vector<std::string> opened;const char *source=(const char *)1;
    // Nothing installed anywhere: no provider, and no stale source text.
    auto none=CDV3ResolveHookFunctionWith([&](const char *path){opened.push_back(path);return (void *)nullptr;},
        [](void *,const char *){return (void *)nullptr;},&source);
    assert(!none && !source && opened.size()==4);
    assert(opened[0]=="/var/jb/usr/lib/libsubstrate.dylib"); // the beta 5 path is still tried first
    // The original path wins whenever it works.
    auto first=CDV3ResolveHookFunctionWith([](const char *){return (void *)0x10;},
        [](void *handle,const char *name){return handle==(void *)0x10 && !strcmp(name,"MSHookFunction")?(void *)Hook:(void *)nullptr;},&source);
    assert(first==Hook && !strcmp(source,"/var/jb/usr/lib/libsubstrate.dylib"));
    // A library that opens but lacks the symbol is skipped, not trusted.
    auto second=CDV3ResolveHookFunctionWith(
        [](const char *path){return !strcmp(path,"/var/jb/usr/lib/libsubstrate.dylib")?(void *)0x10:!strcmp(path,"/var/jb/usr/lib/libellekit.dylib")?(void *)0x20:(void *)nullptr;},
        [](void *handle,const char *){return handle==(void *)0x20?(void *)Other:(void *)nullptr;},&source);
    assert(second==Other && !strcmp(source,"/var/jb/usr/lib/libellekit.dylib"));
    // Only when no file provides it is an already-loaded image accepted.
    auto loaded=CDV3ResolveHookFunctionWith([](const char *){return (void *)nullptr;},
        [](void *handle,const char *){return handle==RTLD_DEFAULT?(void *)Hook:(void *)nullptr;},&source);
    assert(loaded==Hook && !strcmp(source,"already-loaded image"));
    // The real resolver must not crash on a host without any provider.
    (void)CDV3ResolveHookFunction(&source);
    puts("Hook provider resolution cases passed");return 0;
}
