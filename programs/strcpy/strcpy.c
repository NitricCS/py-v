#include <stdio.h>
#include <string.h>

int main()
{
    volatile char * result1 = (char*) 2048;
	volatile char * result2 = (char*) 2082;

	char str1[]="Sample";
	char str2[]="Template to override";
	char str3[40];
	strcpy (str2,str1);
	strcpy (str3,"copied");
	strcpy(result1, str2);
	strcpy(result2, str3);

	while(1);
}