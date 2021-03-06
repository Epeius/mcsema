#include <stdio.h>

typedef int (*callback)(int a1, int a2, int a3, int a4, int a5, int a6);

int f1(int a1, int a2, int a3, int a4, int a5, int a6) {
    printf("in f1: %08x, %08x, %08x, %08x, %08x, %08x\n", a1, a2, a3, a4, a5, a6);
    return 0xABCDEF0;
}

int f2(int a1, int a2, int a3, int a4, int a5, int a6) {
    int p  = printf("in f2: %08x, %08x, %08x, %08x, %08x, %08x\n", a1, a2, a3, a4, a5, a6);
    callback c2 = NULL;

    //// ensure assignment to variable is not optimized out
    if(p == 0x10001) {
        c2 = f2;
    } else {
        // should always go here
        c2 = f1;
    }
    //
    //// invokes recursive do_call_value in mcsema
    int rv = c2(a1, a2, a3, a4, a5, a6);
    printf("done with c2: %08x\n", rv);
    printf("done with f1: %08x,\n", a1);
    return 0x1badf00d;
}

int main(int argc, const char* argv[]) {

    callback c = NULL;

    // try to always call c2 but prevent the compiler from optimizing the callback
    int a1 = 0x100, a2 = 0x200, a3 = 0x300, a4 = 0x400, a5 = 0x500, a6 = 0x600;
    if(argc > 100) {
        c = f1;
    } else {
        c = f2;
    }

    for(int i = 0; i < 10; i++) {
        int rv = c(a1, a2, a3, a4, a5, a6);
        printf("done with c[%d]: %08x, %08x, %08x, %08x, %08x, %08x\n", i, a1, a2, a3, a4, a5, a6);
        printf("rv = %08x\n", rv);
    }
    
    return 0;
}
