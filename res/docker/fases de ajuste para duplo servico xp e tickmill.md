## Plano incremental (testar a cada passo)

### Fase 0 — Baseline (hoje, sem mudar código)
Confirme que o container atual ainda funciona.

```bash
cd /mnt/e/dev/MT5-Docker
VNC_PASSWORD=test RUN_MT5=1 docker compose up mt5-server
```

**Teste:** TigerVNC em `127.0.0.1:5901` → MT5 abre e mantém login.

---

### Fase 1 — Renomear + `.env` ✅
- Renomear `mt5-server` → `mt5-tickmill`
- Criar `.env.example` com credenciais Tickmill + `VNC_PASSWORD`
- Remover porta **5555** (não usada) por enquanto

**Teste:**
```bash
cd /mnt/e/dev/MT5-Docker
cp .env.example .env   # ajustar VNC_PASSWORD
docker compose --profile tickmill up mt5-tickmill
```

---

### Fase 2 — Segundo serviço (XP), ainda sem bridge
Duplicar serviço no compose:

| | Tickmill | XP |
|---|----------|-----|
| serviço | `mt5-tickmill` | `mt5-xp` |
| volume | `mt5_tickmill_data` | `mt5_xp_data` |
| VNC | `5901` | `5902` |
| profile | `[tickmill]` | `[xp]` |

**Teste:**
```bash
docker compose --profile tickmill up -d   # só Tickmill
docker compose --profile xp up -d         # só XP
docker compose ps
```

Instalação XP: VNC manual com instalador da XP (não o `mt5setup` genérico).

---

### Fase 3 — Estabilizar MT5 no container
Ajustes pequenos no `entrypoint.sh`:
- `MT5_CMD_OPTIONS=/portable` (isolamento)
- `MT5_SETUP_URL` por serviço (Tickmill vs XP)
- healthcheck simples (processo `terminal64.exe` vivo)

**Teste:** reiniciar container → MT5 volta, login persiste no volume.

---

### Fase 4 — Bridge (desbloqueia o adaptador)
**Ainda não existe no Docker.** Ordem sugerida:

1. **Curto prazo:** bridge continua no **Windows** (`prepararRPyC.bat`) para testes do adaptador enquanto o Docker amadurece.
2. **Médio prazo:** bridge **dentro do container** (Python + `MetaTrader5` sob Wine) — expor porta **18812/18813**.
3. **Alternativa:** EA/WebSocket (já previsto no `nt_mt5`) se Wine+Python for instável.

**Teste adaptador** (só após Fase 4):
```cmd
set MT5_HOST=127.0.0.1 && set MT5_PORT=18812 && ... homologation\run_closed_market.py
```

---

## Ordem recomendada para começar **agora**

1. **Fase 0** — validar baseline  
2. **Fase 1** — renomear + `.env`  
3. **Fase 2** — segundo serviço XP (só VNC/MT5)  
4. Parar aqui até MT5 estável nos dois containers  
5. **Fase 4** — bridge (maior risco técnico)

---

## O que testar em cada camada

| Camada | Como testar | Adaptador? |
|--------|-------------|------------|
| Wine + VNC | TigerVNC, login manual | Não |
| 2 containers isolados | `compose ps`, volumes separados | Não |
| Bridge RPyC | script Python ou curl na porta | **Sim** |
| Adaptador | homologation / `connect_with_external_rpyc.py` | **Sim** |

---
