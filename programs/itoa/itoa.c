#include <stdlib.h>
#include <string.h>

int main() {
    int number = 123;
    char buffer[] = "a";

    int l = 10;
	char *result = (char *)malloc((l+1) * sizeof(char));
    
    itoa(number, buffer, 10);

    strcpy(result, buffer);
	printf("itoa result: %s\n", result);

    return 0;
}