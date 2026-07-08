FROM postgres:16-alpine

COPY init-lex-mwl.sql /docker-entrypoint-initdb.d/10-lex-mwl.sql
COPY sync-password.sh /usr/local/bin/lex-sync-password.sh
COPY docker-entrypoint-lex.sh /usr/local/bin/docker-entrypoint-lex.sh
RUN chmod +x /usr/local/bin/lex-sync-password.sh /usr/local/bin/docker-entrypoint-lex.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint-lex.sh"]
CMD ["postgres"]
