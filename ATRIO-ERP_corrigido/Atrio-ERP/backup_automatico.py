
from datetime import datetime
from pathlib import Path
import os
import sqlite3
import sys
import time

# Pasta principal do projeto
PROJETO = Path(__file__).resolve().parent

# Banco de dados do Átrio ERP
BANCO = PROJETO / "data" / "atrio.db"

# Pasta onde os backups serão guardados
PASTA_BACKUP = Path.home() / "Documents" / "ATRIO-ERP-Backups"


def criar_backup():
    print("Iniciando backup do Átrio ERP...")

    # Verifica se o banco de dados existe
    if not BANCO.is_file():
        print("ERRO: Banco de dados não encontrado.")
        print(f"Local procurado: {BANCO}")
        return False

    # Cria a pasta dos backups
    PASTA_BACKUP.mkdir(parents=True, exist_ok=True)

    # Gera um nome diferente para cada backup
    data = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")

    destino = PASTA_BACKUP / f"atrio_backup_{data}.db"
    temporario = PASTA_BACKUP / f"atrio_backup_{data}.tmp"

    origem = None
    copia = None

    try:
        # Abre o banco original somente para leitura
        endereco = BANCO.resolve().as_uri() + "?mode=ro"

        origem = sqlite3.connect(
            endereco,
            uri=True,
            timeout=30
        )

        # Cria um novo arquivo de backup
        copia = sqlite3.connect(
            str(temporario),
            timeout=30
        )

        # Faz uma cópia segura do banco SQLite
        origem.backup(copia)

        # Verifica se a cópia está íntegra
        resultado = copia.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if resultado != "ok":
            raise RuntimeError(
                f"Erro de integridade: {resultado}"
            )

        # Confirma se existem tabelas
        quantidade = copia.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table'"
        ).fetchone()[0]

        if quantidade == 0:
            raise RuntimeError(
                "O banco copiado não possui tabelas."
            )

        # Fecha as conexões antes de renomear
        copia.close()
        copia = None

        origem.close()
        origem = None

        # Tenta renomear o arquivo até 5 vezes
        for tentativa in range(5):
            try:
                os.replace(temporario, destino)
                break
            except PermissionError:
                if tentativa == 4:
                    raise
                time.sleep(1)

        print()
        print("==================================")
        print("BACKUP REALIZADO COM SUCESSO!")
        print("==================================")
        print(f"Arquivo: {destino}")
        print("Integridade: OK")
        print(f"Tabelas verificadas: {quantidade}")

        return True

    except Exception as erro:
        print()
        print(f"ERRO AO CRIAR BACKUP: {erro}")
        return False

    finally:
        # Garante que nenhuma conexão fique aberta
        if copia is not None:
            copia.close()

        if origem is not None:
            origem.close()

        # Remove arquivos temporários, se possível
        if temporario.exists():
            try:
                temporario.unlink()
            except PermissionError:
                print(
                    "AVISO: O Windows manteve "
                    "um arquivo temporario bloqueado."
                )


if __name__ == "__main__":
    sucesso = criar_backup()
    sys.exit(0 if sucesso else 1)
