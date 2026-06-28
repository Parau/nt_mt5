## Resposta direta

**Sua impressão está correta.** Um único MT5 **não opera duas corretoras ao mesmo tempo** — só **troca de conta** dentro do mesmo terminal.

### O que o MT5 permite (documentação oficial MetaQuotes)

1. **Várias contas no mesmo terminal** — inclusive de corretoras diferentes — mas **apenas uma conectada por vez**. Troca com duplo clique no Navigator ([Manage Trading Accounts](https://www.metatrader5.com/en/terminal/help/start_advanced/account_manage)).
2. **Operação simultânea** exige **várias instâncias do MT5 em diretórios diferentes** ([Platform Installation](https://www.metatrader5.com/en/terminal/help/start_advanced/installation)): *"If you need to work with multiple accounts simultaneously, install the appropriate number of platforms in different directories."*
3. **Duas cópias não rodam no mesmo diretório** ([Platform Start](https://www.metatrader5.com/en/terminal/help/start_advanced/start)).

Para automação (EA, Python, RPyC), consenso de desenvolvedores: **1 terminal = 1 conta ativa = 1 contexto de trading**. Alternar login desconecta a outra corretora e quebra streams/ordens em curso.

### O que isso implica para o adaptador `nt_mt5`

O projeto **já assume um terminal por sessão**:

- RPyC liga ao terminal que está aberto (`testing_contract.md`: *"The RPyC bridge binds to whichever session is open"*).
- Tickmill ↔ XP hoje = **trocar login manualmente** e mudar `VenueProfile` (`TICKMILL_DEMO_PROFILE` vs `XP_B3_PROFILE`).
- Cada config tem **um** `venue_profile`; Tickmill e XP têm capacidades diferentes (ex.: TradeTick).

**Certeza: ~98%** no lado MT5/adaptador (documentação oficial + design do projeto).

### Arquitetura recomendada (Docker + Wine)

| Abordagem | Veredicto |
|-----------|-----------|
| 1 container Tickmill + 1 container XP | **Correto** |
| 1 MT5 alternando login Tickmill/XP | **Só para homologação sequencial**, não para operar os dois juntos |
| 1 MT5 “multibroker” simultâneo | **Não suportado pelo MT5** |

```
Adaptador (Nautilus)          Docker host
┌─────────────────┐          ┌──────────────────────┐
│ TradingNode     │──:18812──│ mt5-tickmill (Wine)  │
│                 │──:18813──│ mt5-xp (Wine)        │
└─────────────────┘          └──────────────────────┘
     ↑ 2 clientes MT5, portas/host distintos, 1 venue_profile cada
```

- **Porta RPyC distinta** por container (`18812`, `18813`, …).
- **Instalador MT5 da corretora** no container certo (XP costuma exigir build própria).
- Modo **`/portable`** para isolar dados/config.
- No adaptador: **dois clientes** (host/port + profile diferentes) ou **dois TradingNodes** separados.

**Certeza da arquitetura Docker: ~90%** — alinhada ao MT5 e ao adaptador; incerteza restante é operacional (Wine, estabilidade, GUI/VNC, latência), não conceitual.

### Resumo

- **Não** use um único MT5 para Tickmill + XP em paralelo.
- **Sim**, use **1 Docker/instância MT5 por corretora**, cada um com bridge RPyC próprio.
- O adaptador suporta isso via **`EXTERNAL_RPYC`** com endpoints separados; operação simultânea exige **dois clientes/configs**, não alternar login no mesmo terminal.

Se quiser, no próximo passo posso esboçar um `docker-compose` mínimo (Tickmill + XP) alinhado ao `prepararRPyC.bat` e ao contrato `EXTERNAL_RPYC` do projeto.