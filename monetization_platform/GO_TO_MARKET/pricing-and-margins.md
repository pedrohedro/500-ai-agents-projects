# 💰 Preços e Margem

Números conforme a configuração padrão em `config.py` (todos ajustáveis por variável de ambiente).

## Pacotes de crédito

| Plano | Preço | Créditos | Preço/crédito |
|---|---|---|---|
| **Starter** | US$ 19 | 1.000 | US$ 0,019 |
| **Pro** | US$ 79 | 5.000 | US$ 0,0158 |
| **Business** | US$ 299 | 25.000 | US$ 0,012 |

Bônus de cadastro: **25 créditos grátis** (seu "teste grátis" embutido).
Preço de referência do crédito avulso: **US$ 0,02**.

## Custo por chamada (em créditos) e receita equivalente

| Produto | Créditos/uso | Receita (plano Starter) |
|---|---|---|
| Suporte (por mensagem) | 1 | ~US$ 0,019 |
| RH (por currículo) | 3 | ~US$ 0,057 |
| Marketing (por geração) | 5 | ~US$ 0,095 |
| Jurídico (por documento) | 8 | ~US$ 0,152 |

## A matemática da margem

O custo real está nos **tokens da OpenRouter**. Usando `deepseek/deepseek-v4-flash`
(~US$ 0,09 / 1M entrada, US$ 0,18 / 1M saída):

- Uma geração de marketing (~1.000 tokens) custa a você **≈ US$ 0,0002**.
- Você cobra **≈ US$ 0,095** por ela.
- **Margem bruta ≈ 99%** (mesmo somando infra/hospedagem, fica bem acima de 90%).

Isso vale para os 4 produtos: como os modelos open-source são 10–50x mais baratos
que os proprietários, a margem por chamada é altíssima. O que corrói a margem não é
o token — é **infra ociosa** e **abuso** (por isso a plataforma já tem medição por uso
e bloqueio 402 sem créditos).

## Como precificar na prática

1. **Não compita por preço** — o custo é irrelevante. Precifique pelo **valor**:
   quanto o cliente economiza (horas de redator/advogado/atendente).
2. **Ancoragem**: deixe o Business visível para o Pro parecer barato.
3. **Assinatura > avulso**: transforme os pacotes em recarga mensal automática para
   receita recorrente (MRR). O Stripe suporta; basta criar um Price recorrente.
4. **Teste grátis generoso**: os 25 créditos deixam o cliente sentir o valor antes de pagar.

## Alavancas de receita (env vars)

| Variável | Efeito |
|---|---|
| `PACK_*_PRICE` / `PACK_*_CREDITS` | ajusta preço e tamanho dos pacotes |
| `COST_MARKETING/LEGAL/SUPPORT/HR` | quanto cada chamada consome |
| `SIGNUP_BONUS_CREDITS` | tamanho do teste grátis |
| `CREDIT_PRICE_USD` | preço de referência do crédito |
