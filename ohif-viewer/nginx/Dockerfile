FROM nginx:1.27-alpine

RUN rm -f /etc/nginx/conf.d/default.conf

COPY 00-lex-security.conf /etc/nginx/conf.d/00-lex-security.conf
COPY gateway.conf /etc/nginx/conf.d/default.conf
