import argparse
import datetime
import decimal
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid


CAMPOS_PEDIDO = {"id", "clienteId", "clienteNome", "status", "total", "criadoEm"}
CAMPOS_PAGINA = {"content", "page", "size", "totalElements", "totalPages", "first", "last"}


class Validacao:
    def __init__(self, argumentos):
        self.argumentos = argumentos
        self.checagens = []
        self.requisicoes = 0
        self.inicio = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def verificar(self, condicao, descricao):
        if not condicao:
            raise ValueError(descricao)
        self.checagens.append(descricao)

    def chamar(self, metodo, caminho, tenant=None, corpo=None, status=200, gerenciamento=False):
        base = self.argumentos.management_url if gerenciamento else self.argumentos.api_url
        cabecalhos = {"Accept": "application/json"}
        if tenant is not None:
            cabecalhos["tenantId"] = str(tenant)
        dados = None
        if corpo is not None:
            dados = json.dumps(corpo).encode("utf-8")
            cabecalhos["Content-Type"] = "application/json"
        requisicao = urllib.request.Request(base.rstrip("/") + caminho, dados, cabecalhos, method=metodo)
        self.requisicoes += 1
        try:
            with urllib.request.urlopen(requisicao, timeout=10) as resposta:
                codigo = resposta.status
                conteudo = resposta.read()
        except urllib.error.HTTPError as erro:
            codigo = erro.code
            conteudo = erro.read()
        self.verificar(codigo == status, f"{metodo} {caminho}: HTTP {status}, recebido {codigo}")
        if not conteudo:
            return None
        return json.loads(conteudo)

    def validar_pedido(self, pedido, cliente, ids):
        self.verificar(set(pedido) == CAMPOS_PEDIDO, "Pedido contém somente os campos do DTO")
        self.verificar(type(pedido["id"]) is int and pedido["id"] in ids, "Pedido pertence à empresa consultada")
        self.verificar(type(pedido["clienteId"]) is int and pedido["clienteId"] == cliente["id"], "Cliente do pedido pertence à empresa")
        self.verificar(type(pedido["clienteNome"]) is str and pedido["clienteNome"] == cliente["nome"], "Nome do cliente preservado")
        self.verificar(type(pedido["status"]) is str and pedido["status"] in {"ABERTO", "CONFIRMADO", "CANCELADO"}, "Status válido")
        self.verificar(type(pedido["total"]) in (int, float), "Total possui tipo numérico")
        self.verificar(decimal.Decimal(str(pedido["total"])) == decimal.Decimal("30.00"), "Total calculado: três itens de 10,00")
        self.verificar(type(pedido["criadoEm"]) is str, "Data do pedido possui representação textual")
        instante = datetime.datetime.fromisoformat(pedido["criadoEm"].replace("Z", "+00:00"))
        self.verificar(instante.tzinfo is not None, "Data do pedido contém fuso horário")

    def validar_pagina(self, pagina, empresa, numero, tamanho, ordem):
        self.verificar(set(pagina) == CAMPOS_PAGINA, "Página contém somente os campos do DTO")
        self.verificar(type(pagina["content"]) is list, "Conteúdo da página é uma lista")
        for campo in ("page", "size", "totalElements", "totalPages"):
            self.verificar(type(pagina[campo]) is int, f"Campo {campo} possui tipo inteiro")
        self.verificar(type(pagina["first"]) is bool and type(pagina["last"]) is bool, "Indicadores de página possuem tipo booleano")
        self.verificar(pagina["page"] == numero and pagina["size"] == tamanho, "Número e tamanho da página preservados")
        total_paginas = (3 + tamanho - 1) // tamanho
        self.verificar(pagina["totalElements"] == 3 and pagina["totalPages"] == total_paginas, "Paginação informa os três pedidos da empresa")
        self.verificar(pagina["first"] == (numero == 0), "Indicador da primeira página correto")
        self.verificar(pagina["last"] == (numero + 1 >= total_paginas), "Indicador da última página correto")
        self.verificar([pedido["id"] for pedido in pagina["content"]] == ordem, "Ordem dos pedidos e limite da página corretos")
        for pedido in pagina["content"]:
            self.validar_pedido(pedido, empresa["cliente"], empresa["pedidos"])

    def metrica(self, nome, resultado=None):
        caminho = "/actuator/metrics/" + nome
        if resultado is not None:
            caminho += "?" + urllib.parse.urlencode({"tag": "result:" + resultado})
        resposta = self.chamar("GET", caminho, gerenciamento=True)
        valores = [medida["value"] for medida in resposta["measurements"] if medida["statistic"] == "COUNT"]
        self.verificar(len(valores) == 1, f"Contador disponível: {nome} {resultado or ''}".strip())
        return valores[0]

    def contadores(self):
        return {resultado: self.metrica("tcc.cache.requests", resultado) for resultado in ("hit", "miss", "fallback")}

    def validar_variacao(self, antes, depois, esperado):
        variacao = {chave: depois[chave] - antes[chave] for chave in antes}
        self.verificar(variacao == esperado, f"Variação dos contadores de cache: {esperado}")

    def sem_cache(self):
        lote = "TCC-validacao-" + uuid.uuid4().hex[:16]
        manifesto = {"versao": 1, "lote": lote, "api_url": self.argumentos.api_url, "empresas": [], "paginas": []}
        for numero in (1, 2):
            empresa = self.chamar("POST", "/api/empresas", corpo={"nome": f"{lote}-empresa-{numero}"}, status=201)
            self.verificar(set(empresa) == {"id", "nome"} and type(empresa["id"]) is int, "Empresa retornada como DTO")
            cliente = self.chamar("POST", "/api/clientes", empresa["id"], {"nome": f"{lote}-cliente-{numero}"}, 201)
            self.verificar(set(cliente) == {"id", "tenantId", "nome"} and cliente["tenantId"] == empresa["id"], "Cliente retornado como DTO da empresa")
            empresa["cliente"] = cliente
            empresa["pedidos"] = []
            for indice in range(3):
                corpo = {"clienteId": cliente["id"], "itens": [{"descricao": f"{lote}-item-{indice}-{item}", "quantidade": 1, "precoUnitario": 10} for item in range(3)]}
                pedido = self.chamar("POST", "/api/pedidos", empresa["id"], corpo, 201)
                empresa["pedidos"].append(pedido["id"])
                self.validar_pedido(pedido, cliente, empresa["pedidos"])
                if indice:
                    status = "CONFIRMADO" if indice == 1 else "CANCELADO"
                    atualizado = self.chamar("PATCH", f"/api/pedidos/{pedido['id']}/status", empresa["id"], {"status": status})
                    self.verificar(atualizado["status"] == status, "Status inicial do pedido alterado")
            manifesto["empresas"].append(empresa)
        primeira, segunda = manifesto["empresas"]
        self.verificar(primeira["id"] != segunda["id"], "Empresas de validação possuem identificadores distintos")
        corpo_invalido = {"clienteId": segunda["cliente"]["id"], "itens": [{"descricao": lote, "quantidade": 1, "precoUnitario": 10}]}
        self.chamar("POST", "/api/pedidos", primeira["id"], corpo_invalido, 404)
        self.chamar("PATCH", f"/api/pedidos/{primeira['pedidos'][0]}/status", segunda["id"], {"status": "CANCELADO"}, 404)
        self.chamar("GET", "/api/pedidos", status=400)
        self.chamar("GET", "/api/pedidos?page=-1", primeira["id"], status=400)
        self.chamar("GET", "/api/pedidos?size=101", primeira["id"], status=400)
        self.chamar("GET", "/api/pedidos?sort=tenantId,asc", primeira["id"], status=400)
        for empresa in manifesto["empresas"]:
            ids = sorted(empresa["pedidos"])
            consultas = [
                ("/api/pedidos?page=0&size=2&sort=id,asc", 0, 2, ids[:2]),
                ("/api/pedidos?page=1&size=2&sort=id,asc", 1, 2, ids[2:]),
                ("/api/pedidos?page=2&size=2&sort=id,asc", 2, 2, []),
                ("/api/pedidos?page=0&size=2&sort=id,desc", 0, 2, list(reversed(ids))[:2]),
                ("/api/pedidos", 0, 20, list(reversed(ids))),
            ]
            for caminho, pagina, tamanho, ordem in consultas:
                resposta = self.chamar("GET", caminho, empresa["id"])
                self.validar_pagina(resposta, empresa, pagina, tamanho, ordem)
                manifesto["paginas"].append({"tenantId": empresa["id"], "caminho": caminho, "resposta": resposta})
        salvar_novo(self.argumentos.manifest, manifesto)
        return {"lote": lote, "empresas": [empresa["id"] for empresa in manifesto["empresas"]], "pedidos_criados": 6, "manifesto": str(self.argumentos.manifest)}

    def cache(self):
        manifesto = json.loads(self.argumentos.manifest.read_text(encoding="utf-8"))
        self.verificar(manifesto.get("versao") == 1 and str(manifesto.get("lote", "")).startswith("TCC-validacao-"), "Manifesto identificado como dados próprios de validação")
        self.verificar(len(manifesto["empresas"]) == 2, "Manifesto contém as duas empresas de validação")
        tenant_ids = {empresa["id"] for empresa in manifesto["empresas"]}
        self.verificar(all(pagina["tenantId"] in tenant_ids and pagina["caminho"].startswith("/api/pedidos") for pagina in manifesto["paginas"]), "Todas as consultas permanecem nos tenants próprios")
        primaria = manifesto["paginas"][0]
        antes = self.contadores()
        primeira = self.chamar("GET", primaria["caminho"], primaria["tenantId"])
        depois_falta = self.contadores()
        self.verificar(primeira == primaria["resposta"], "Primeira leitura com cache equivale à resposta sem cache")
        self.validar_variacao(antes, depois_falta, {"hit": 0, "miss": 1, "fallback": 0})
        segunda = self.chamar("GET", primaria["caminho"], primaria["tenantId"])
        depois_acerto = self.contadores()
        self.verificar(segunda == primeira, "Acerto do cache preserva integralmente a resposta")
        self.validar_variacao(depois_falta, depois_acerto, {"hit": 1, "miss": 0, "fallback": 0})
        for pagina in manifesto["paginas"]:
            resposta = self.chamar("GET", pagina["caminho"], pagina["tenantId"])
            self.verificar(resposta == pagina["resposta"], "Conteúdo, ordem, paginação, totais e status equivalentes entre os modos")
        empresa = manifesto["empresas"][0]
        pedido_id = empresa["pedidos"][0]
        self.verificar(next(pedido for pedido in primeira["content"] if pedido["id"] == pedido_id)["status"] == "ABERTO", "Pedido escolhido permanece aberto antes da alteração real")
        invalidacoes_antes = self.metrica("tcc.cache.invalidations")
        alterado = self.chamar("PATCH", f"/api/pedidos/{pedido_id}/status", empresa["id"], {"status": "CONFIRMADO"})
        self.verificar(alterado["status"] == "CONFIRMADO", "Alteração real confirmada na API")
        invalidacoes_depois = self.metrica("tcc.cache.invalidations")
        self.verificar(invalidacoes_depois - invalidacoes_antes == 1, "Alteração real invalida uma geração de cache")
        contadores_antes = self.contadores()
        pagina_atualizada = self.chamar("GET", primaria["caminho"], empresa["id"])
        self.validar_variacao(contadores_antes, self.contadores(), {"hit": 0, "miss": 1, "fallback": 0})
        esperado = json.loads(json.dumps(primaria["resposta"]))
        for pedido in esperado["content"]:
            if pedido["id"] == pedido_id:
                pedido["status"] = "CONFIRMADO"
        self.verificar(pagina_atualizada == esperado, "Leitura após invalidação reflete somente a alteração realizada")
        outra_pagina = next(pagina for pagina in manifesto["paginas"] if pagina["tenantId"] != empresa["id"])
        contadores_antes = self.contadores()
        outra_resposta = self.chamar("GET", outra_pagina["caminho"], outra_pagina["tenantId"])
        self.verificar(outra_resposta == outra_pagina["resposta"], "Alteração em uma empresa preserva os pedidos da outra")
        self.validar_variacao(contadores_antes, self.contadores(), {"hit": 1, "miss": 0, "fallback": 0})
        self.chamar("PATCH", f"/api/pedidos/{pedido_id}/status", empresa["id"], {"status": "CONFIRMADO"})
        self.verificar(self.metrica("tcc.cache.invalidations") == invalidacoes_depois, "Repetir o status não provoca invalidação")
        contadores_antes = self.contadores()
        self.verificar(self.chamar("GET", primaria["caminho"], empresa["id"]) == esperado, "Repetir o status preserva a resposta")
        self.validar_variacao(contadores_antes, self.contadores(), {"hit": 1, "miss": 0, "fallback": 0})
        return {"lote": manifesto["lote"], "empresas": sorted(tenant_ids), "contadores_apos_primeira_falta": depois_falta, "contadores_apos_primeiro_acerto": depois_acerto, "invalidacoes_antes": invalidacoes_antes, "invalidacoes_depois": invalidacoes_depois, "ttl": "Verificação externa pelo administrador; este script não espera a expiração."}


def salvar_novo(caminho, conteudo):
    with caminho.open("x", encoding="utf-8") as arquivo:
        json.dump(conteudo, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("sem-cache", "cache"), required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--api-url", default="http://10.10.10.10:8080")
    parser.add_argument("--management-url", default="http://127.0.0.1:8081")
    argumentos = parser.parse_args()
    if argumentos.output.resolve() == argumentos.manifest.resolve():
        parser.error("O relatório e o manifesto devem usar caminhos distintos.")
    if argumentos.output.exists() or not argumentos.output.parent.is_dir():
        parser.error("O relatório deve ser um arquivo novo em uma pasta existente.")
    if argumentos.phase == "sem-cache" and (argumentos.manifest.exists() or not argumentos.manifest.parent.is_dir()):
        parser.error("O manifesto deve ser um arquivo novo em uma pasta existente.")
    if argumentos.phase == "cache" and not argumentos.manifest.is_file():
        parser.error("A fase com cache exige o manifesto gerado na fase sem cache.")
    validacao = Validacao(argumentos)
    relatorio = {"fase": argumentos.phase, "inicio": validacao.inicio, "sucesso": False}
    codigo = 0
    try:
        detalhes = validacao.sem_cache() if argumentos.phase == "sem-cache" else validacao.cache()
        relatorio.update(detalhes)
        relatorio["sucesso"] = True
    except Exception as erro:
        relatorio["erro"] = str(erro)
        codigo = 1
    relatorio["fim"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    relatorio["checagens_aprovadas"] = len(validacao.checagens)
    relatorio["requisicoes"] = validacao.requisicoes
    salvar_novo(argumentos.output, relatorio)
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    return codigo


if __name__ == "__main__":
    sys.exit(main())
