#include <stdlib.h>
#include <stdio.h>
int main()
{
    volatile unsigned * result = (unsigned*) 2048;
    int i;
    char buffer[] = "1234";
    i = atoi (buffer);
    *result = i;

    while(1);
}