// SPDX-License-Identifier: GPL-3.0-only
// Reuse the confirmed Tesla address. Never change/remove an existing alias,
// the original CarDash address, routing tables, DNS, or saved preferences.
#include <arpa/inet.h>
#include <errno.h>
#include <ifaddrs.h>
#include <net/if.h>
#include <stdint.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/sockio.h>
#include <unistd.h>

static const char address[] = "100.99.10.2";
typedef int (*CDLookup)(char *, size_t);
typedef int (*CDAdd)(void);

static int lookup(char *interface, size_t capacity) {
    struct in_addr target;
    if (inet_pton(AF_INET, address, &target) != 1) return EINVAL;
    struct ifaddrs *list = NULL;
    if (getifaddrs(&list) != 0) return errno;
    int result = EADDRNOTAVAIL;
    for (struct ifaddrs *entry = list; entry; entry = entry->ifa_next) {
        if (!entry->ifa_addr || entry->ifa_addr->sa_family != AF_INET) continue;
        struct sockaddr_in *value = (struct sockaddr_in *)entry->ifa_addr;
        if (value->sin_addr.s_addr == target.s_addr) {
            if (strlcpy(interface, entry->ifa_name, capacity) >= capacity) result = ENAMETOOLONG;
            else result = 0;
            break;
        }
    }
    freeifaddrs(list);
    return result;
}

static int add_alias(void) {
    if (geteuid() != 0) return EPERM;
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) return errno;
    struct ifaliasreq request;
    memset(&request, 0, sizeof request);
    strlcpy(request.ifra_name, "lo0", sizeof request.ifra_name);
    struct sockaddr_in alias = {.sin_len = sizeof alias, .sin_family = AF_INET};
    struct sockaddr_in mask = {.sin_len = sizeof mask, .sin_family = AF_INET};
    inet_pton(AF_INET, address, &alias.sin_addr);
    mask.sin_addr.s_addr = htonl(UINT32_MAX);
    memcpy(&request.ifra_addr, &alias, sizeof alias);
    memcpy(&request.ifra_mask, &mask, sizeof mask);
    int result = ioctl(fd, SIOCAIFADDR, &request) == 0 ? 0 : errno;
    close(fd);
    return result;
}

#ifndef CD_NETWORK_TEST
static
#endif
int cd_network_ensure_with(CDLookup find, CDAdd add, char *interface,
                           size_t capacity, int *added) {
    if (!find || !add || !interface || capacity < IFNAMSIZ || !added) return EINVAL;
    interface[0] = 0;
    *added = 0;
    int found = find(interface, capacity);
    if (!found) return strcmp(interface, "lo0") == 0 ? 0 : EADDRINUSE;
    if (found != EADDRNOTAVAIL) return found;
    int error = add();
    interface[0] = 0;
    found = find(interface, capacity);
    if (!found) {
        if (strcmp(interface, "lo0") != 0) return EADDRINUSE;
        *added = error == 0;
        return 0;
    }
    return error ? error : found;
}

int cd_network_ensure(char *interface, size_t capacity, int *added) {
    return cd_network_ensure_with(lookup, add_alias, interface, capacity, added);
}
