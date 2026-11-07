// SPDX-License-Identifier: GPL-3.0-only
// Small checked OpenSSL 3 bridge; no keys or authentication bypasses.
#include <openssl/evp.h>
#include <openssl/ec.h>
#include <openssl/pem.h>
#include <openssl/x509.h>
#include <openssl/pkcs7.h>
#include <limits.h>

int cp_public(int curve,const unsigned char *seed,unsigned char *out){
 EVP_PKEY *k=EVP_PKEY_new_raw_private_key(curve?EVP_PKEY_X25519:EVP_PKEY_ED25519,NULL,seed,32);
 size_t n=32;int ok=k&&EVP_PKEY_get_raw_public_key(k,out,&n)==1&&n==32;EVP_PKEY_free(k);return ok;
}
int cp_shared(const unsigned char *seed,const unsigned char *public,unsigned char *out){
 EVP_PKEY *a=EVP_PKEY_new_raw_private_key(EVP_PKEY_X25519,NULL,seed,32),*b=EVP_PKEY_new_raw_public_key(EVP_PKEY_X25519,NULL,public,32);
 EVP_PKEY_CTX *c=a?EVP_PKEY_CTX_new(a,NULL):NULL;size_t n=32;
 int ok=c&&b&&EVP_PKEY_derive_init(c)==1&&EVP_PKEY_derive_set_peer(c,b)==1&&EVP_PKEY_derive(c,out,&n)==1&&n==32;
 EVP_PKEY_CTX_free(c);EVP_PKEY_free(a);EVP_PKEY_free(b);return ok;
}
int cp_sign(const unsigned char *seed,const unsigned char *message,int n,unsigned char *out){
 if(n<0||n>8388608)return 0;
 EVP_PKEY *k=EVP_PKEY_new_raw_private_key(EVP_PKEY_ED25519,NULL,seed,32);EVP_MD_CTX *c=EVP_MD_CTX_new();size_t count=64;
 int ok=k&&c&&EVP_DigestSignInit(c,NULL,NULL,NULL,k)==1&&EVP_DigestSign(c,out,&count,message,(size_t)n)==1&&count==64;
 EVP_MD_CTX_free(c);EVP_PKEY_free(k);return ok;
}
int cp_verify(const unsigned char *public,const unsigned char *message,int n,const unsigned char *signature){
 if(n<0||n>8388608)return 0;
 EVP_PKEY *k=EVP_PKEY_new_raw_public_key(EVP_PKEY_ED25519,NULL,public,32);EVP_MD_CTX *c=EVP_MD_CTX_new();
 int ok=k&&c&&EVP_DigestVerifyInit(c,NULL,NULL,NULL,k)==1&&EVP_DigestVerify(c,signature,64,message,(size_t)n)==1;
 EVP_MD_CTX_free(c);EVP_PKEY_free(k);return ok;
}
int cp_crypt(int enc,int aead,const unsigned char *key,const unsigned char *iv,const unsigned char *aad,int an,const unsigned char *in,int n,unsigned char *out){
 if(n<0||n>8388608||an<0||an>65536||(!enc&&aead&&n<16))return -1;
 EVP_CIPHER_CTX *c=EVP_CIPHER_CTX_new();if(!c)return -1;
 int length=0,extra=0,body=n-(!enc&&aead?16:0),ok=0;
 const EVP_CIPHER *cipher=aead?EVP_chacha20_poly1305():EVP_aes_128_ctr();
 if(EVP_CipherInit_ex(c,cipher,NULL,key,iv,enc)!=1)goto done;
 if(aead&&an&&EVP_CipherUpdate(c,NULL,&extra,aad,an)!=1)goto done;
 if(!enc&&aead&&EVP_CIPHER_CTX_ctrl(c,EVP_CTRL_AEAD_SET_TAG,16,(void *)(in+body))!=1)goto done;
 if(EVP_CipherUpdate(c,out,&length,in,body)!=1||EVP_CipherFinal_ex(c,out+length,&extra)!=1)goto done;
 length+=extra;
 if(enc&&aead){if(EVP_CIPHER_CTX_ctrl(c,EVP_CTRL_AEAD_GET_TAG,16,out+length)!=1)goto done;length+=16;}
 ok=1;
done:EVP_CIPHER_CTX_free(c);return ok?length:-1;
}
static EVP_PKEY *private_der(const unsigned char *der,int n){
 if(n<1||n>16384)return NULL;const unsigned char *p=der;return d2i_AutoPrivateKey(NULL,&p,n);
}
int cp_accessory(const unsigned char *der,int dn,const unsigned char *message,int n,unsigned char *out){
 if(n<1||n>4096)return 0;EVP_PKEY *k=private_der(der,dn);EVP_MD_CTX *c=EVP_MD_CTX_new();
 unsigned char signature[256];size_t count=sizeof(signature);ECDSA_SIG *s=NULL;int ok=0;
 if(!k||!c||EVP_DigestSignInit(c,NULL,EVP_sha256(),NULL,k)!=1||EVP_DigestSign(c,signature,&count,message,(size_t)n)!=1)goto done;
 const unsigned char *p=signature;s=d2i_ECDSA_SIG(NULL,&p,(long)count);if(!s)goto done;
 const BIGNUM *r,*v;ECDSA_SIG_get0(s,&r,&v);ok=BN_bn2binpad(r,out,32)==32&&BN_bn2binpad(v,out+32,32)==32;
done:ECDSA_SIG_free(s);EVP_MD_CTX_free(c);EVP_PKEY_free(k);return ok;
}
int cp_certmatch(const unsigned char *der,int dn,const unsigned char *pem,int pn){
 if(pn<1||pn>16384)return 0;EVP_PKEY *k=private_der(der,dn);BIO *bio=BIO_new_mem_buf(pem,pn);X509 *x=bio?PEM_read_bio_X509(bio,NULL,NULL,NULL):NULL;PKCS7 *p7=NULL;
 if(!x){const unsigned char *p=pem;p7=d2i_PKCS7(NULL,&p,pn);if(p7&&PKCS7_type_is_signed(p7)&&p7->d.sign&&sk_X509_num(p7->d.sign->cert)==1)x=X509_dup(sk_X509_value(p7->d.sign->cert,0));}
 EVP_PKEY *public=x?X509_get_pubkey(x):NULL;
 int ok=k&&public&&EVP_PKEY_eq(k,public)==1;EVP_PKEY_free(k);EVP_PKEY_free(public);X509_free(x);BIO_free(bio);PKCS7_free(p7);return ok;
}
