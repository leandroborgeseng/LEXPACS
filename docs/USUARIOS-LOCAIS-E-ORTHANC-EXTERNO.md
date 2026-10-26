# Usuários locais e Orthanc externo (V1–V4, U1–U5)

## Orthanc externo (só por variáveis de ambiente)
- `docker-compose.externo.yml` sobe só portal, viewer e gateway. Não sobe Orthanc, Postgres, Keycloak nem backup.
- `ORTHANC_URL`, `ORTHANC_USERNAME`, `ORTHANC_PASSWORD`: portal e gateway. Nada fixo no repositório.
- O gateway repassa ao Orthanc **só GET/HEAD** em `/dicom-web` e `/wado` (STOW/PUT/DELETE → 403), sempre depois do `auth_request`.
  As credenciais do Orthanc saem do env do gateway; o `Authorization` e os cookies do navegador não chegam ao Orthanc.
- Sem sessão: `/dicom-web` e `/wado` → 401; `/viewer/` → 302 para o login.
- `ORTHANC_EXTERNAL_READONLY=true` (padrão): o portal não grava config/plugins/worklists no Orthanc e não liga MWL/HL7/MPPS/migração no startup.
- Piloto (V4): primeiro num Orthanc de teste; no Orthanc real, só leitura, com usuário de leitura e aprovação do Leandro.

## Usuários locais
- Banco SQLite em `LOCAL_USERS_DB_PATH` (volume `lex-data`), hash Argon2id.
- Perfis: `admin`, `medico`, `tecnico`, `recepcao`, `paciente` (paciente fica para o portal do paciente; não entra na área clínica).
- Só o admin cadastra, inativa, reativa e redefine senha: tela `/clinica/usuarios`, API `/api/admin/users`.
- Senha mínima de 10 caracteres; nunca aparece em resposta, log ou auditoria.
- 5 tentativas erradas bloqueiam a conta por 15 min (`LOGIN_MAX_FAILURES`, `LOGIN_LOCKOUT_MINUTES`).
- Sessão no servidor, expira com 30 min sem uso (`SESSION_IDLE_MINUTES`); logout e inativação derrubam a sessão.
- Admin inicial: `LEX_ADMIN_USER` / `LEX_ADMIN_PASSWORD`, criado só se o banco estiver vazio, com troca obrigatória no 1º acesso (`/clinica/senha`).
  Enquanto a troca estiver pendente, viewer, DICOMweb e admin ficam bloqueados.
- Auditoria (`audit.jsonl`): login, login com falha, troca de senha, cadastro, inativação, reativação e redefinição.

## Perfis e imagens
| Perfil | Viewer/DICOMweb | Assina laudo | Cadastra usuários |
|---|---|---|---|
| admin | sim | sim | sim |
| medico | sim | sim | não |
| tecnico | sim | não | não |
| recepcao | não | não | não |
