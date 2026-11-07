// SPDX-License-Identifier: GPL-3.0-only
// Native launchd entry point: records the exec boundary before entering Python.
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

int main(void) {
    char *args[] = {"/var/jb/usr/bin/python3", "-u",
                    "/var/jb/usr/lib/cardash-v3/backend/server.py", NULL};
    fprintf(stderr, "CarDash V3 service launching (pid %d)\n", getpid());
    execv(args[0], args);
    fprintf(stderr, "CarDash V3 receiver launch failed: %s\n", strerror(errno));
    return 1;
}
