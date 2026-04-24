# Gateway Remoto de Teste (RPyC)

Este documento descreve o papel, o propósito e o funcionamento do gateway remoto RPyC utilizado para validação operacional do adaptador `nt_mt5`.

## Propósito

O gateway remoto é uma **ferramenta operacional de suporte** destinada exclusivamente à validação em tempo real (*live validation*) do adaptador em ambientes onde o terminal MetaTrader 5 (MT5) está disponível nativamente (tipicamente Windows).

Ele permite que desenvolvedores e contribuidores validem a conectividade, a recepção de dados e a execução de ordens contra um terminal MT5 real sem a necessidade de gerenciar o ciclo de vida do terminal através do adaptador.

## Papel no Projeto e Alinhamento Arquitetural

Para evitar ambiguidades, o papel deste gateway é definido pelos seguintes pilares:

1.  **Caso de `external_rpyc`**: O gateway remoto é a implementação concreta do modo de acesso `EXTERNAL_RPYC`. Ele representa um terminal ou bridge que já existe fora do escopo de gerenciamento do adaptador.
2.  **Ferramenta de Validação Operacional**: Seu uso principal é para testes de aceitação e fumaça em ambiente real. Ele não substitui os contratos principais de teste do projeto (stubs/fakes determinísticos).
3.  **Não é `managed_terminal`**: Este gateway **não** é gerenciado pelo adaptador. O adaptador não inicia, supervisiona ou encerra o processo deste gateway.
4.  **Não é `dockerized`**: Embora possa ser executado dentro de um container por conveniência do usuário, este gateway não segue a arquitetura futura de backend `dockerized` prevista para o modo `managed_terminal`.
5.  **Não é uma Arquitetura Concorrente**: O gateway remoto é um componente de infraestrutura/transporte da camada de baixo nível (*venue-native*). Ele não redefine o modelo público de acesso ao terminal nem compete com o design do adaptador.

## Fluxo de Uso

Quando o adaptador é configurado com `terminal_access = MT5TerminalAccessMode.EXTERNAL_RPYC`, ele se conecta a este gateway via RPyC. O gateway atua como um proxy para a biblioteca nativa `MetaTrader5`, executando comandos e devolvendo resultados brutos que o adaptador então normaliza para o domínio do NautilusTrader.

## Relação com outros Documentos

- **`docs/adapter_contract.md`**: Define como o adaptador se integra a este gateway na borda.
- **`docs/terminal_access_contract.md`**: Estabelece o contrato público que o modo `EXTERNAL_RPYC` (implementado por este gateway) deve seguir.
- **`docs/specs/spec_terminal_access_with_gateway.md`**: Contém a especificação técnica detalhada da superfície RPC suportada.

---

**Nota:** Este gateway é considerado uma ferramenta de infraestrutura externa. O suporte oficial e estável do adaptador é construído para consumir este gateway de forma transparente através do contrato `external_rpyc`.
