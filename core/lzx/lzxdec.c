/* lzxdec <entrada_lzx_crua> <saida> <window_bits> <tamanho_saida>
   entrada = blocos LZX ja concatenados (sem os cabecalhos FF uuuu cccc do XMemCompress) */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "mspack.h"
#include "lzx.h"
struct myf { FILE *f; };
#define F(x) (((struct myf*)(x))->f)
static struct mspack_file *o_(struct mspack_system *s, const char *n, int m) { struct myf *x=malloc(sizeof *x); F(x)=fopen(n, m==MSPACK_SYS_OPEN_READ?"rb":"wb"); if(!F(x)){free(x);return NULL;} return (struct mspack_file*)x; }
static void c_(struct mspack_file *x){ fclose(F(x)); free(x); }
static int r_(struct mspack_file *x, void *b, int n){ return (int)fread(b,1,n,F(x)); }
static int w_(struct mspack_file *x, void *b, int n){ return (int)fwrite(b,1,n,F(x)); }
static int s_(struct mspack_file *x, off_t o, int m){ return fseek(F(x),(long)o,m); }
static off_t t_(struct mspack_file *x){ return ftell(F(x)); }
static void m_(struct mspack_file *x, const char *fmt, ...){ (void)x;(void)fmt; }
static void *a_(struct mspack_system *s, size_t n){ return malloc(n); }
static void f_(void *p){ free(p); }
static void cp_(void *a, void *b, size_t n){ memcpy(b,a,n); }
int main(int argc, char **argv){
  if(argc<5){ fprintf(stderr,"uso: lzxdec in out window_bits outlen\n"); return 2; }
  struct mspack_system sys={o_,c_,r_,w_,s_,t_,m_,a_,f_,cp_,NULL};
  struct mspack_file *in=o_(&sys,argv[1],MSPACK_SYS_OPEN_READ), *out=o_(&sys,argv[2],MSPACK_SYS_OPEN_WRITE);
  if(!in||!out){ fprintf(stderr,"erro abrindo arquivos\n"); return 1; }
  long n=atol(argv[4]);
  struct lzxd_stream *z=lzxd_init(&sys,in,out,atoi(argv[3]),0,0x8000,(off_t)n,0);
  if(!z){ fprintf(stderr,"lzxd_init falhou\n"); return 1; }
  int e=lzxd_decompress(z,(off_t)n); lzxd_free(z); c_(in); c_(out);
  if(e){ fprintf(stderr,"erro lzx %d\n",e); return 1; }
  return 0;
}
