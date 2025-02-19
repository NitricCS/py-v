#include <string.h>
int main() {
    unsigned *result = (unsigned *) 2048;
    unsigned val = 1234;
    *result = val;
    memset(result, 0xFF, 1);
    
    while (1);
}