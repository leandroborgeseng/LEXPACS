FROM nginx:1.27-alpine

RUN rm -f /etc/nginx/conf.d/default.conf

# Só as variáveis LEX_ORTHANC_* são substituídas (as $vars do nginx ficam intactas)
ENV NGINX_ENVSUBST_FILTER=^LEX_ORTHANC_

COPY 00-lex-security.conf /etc/nginx/conf.d/00-lex-security.conf
COPY gateway.conf.template /etc/nginx/templates/default.conf.template
COPY 15-lex-orthanc.envsh /docker-entrypoint.d/15-lex-orthanc.envsh
RUN chmod +x /docker-entrypoint.d/15-lex-orthanc.envsh
