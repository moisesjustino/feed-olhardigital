# -*- coding: utf-8 -*-
# scraper.py (versão corrigida para GitHub Actions)

import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from urllib.parse import urljoin
import datetime
import time
import pytz
import re

# Importações adicionais para a espera inteligente do Selenium
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

# --- CONFIGURAÇÕES ---
URL_ALVO = 'https://olhardigital.com.br/editorias/noticias/'
URL_BASE = 'https://olhardigital.com.br'
NOME_ARQUIVO_RSS = 'feed_olhardigital.xml'
FEED_TITULO = 'Olhar Digital - Feed RSS (Deluxe)'
FEED_DESCRICAO = 'Últimas notícias do Olhar Digital, com imagens e resumos.'

# --- SELETORES DA PÁGINA PRINCIPAL ---
SELETOR_CONTAINER_ARTIGOS = 'section.p-block'
SELETOR_ITEM_ARTIGO = 'a.p-item'
SELETOR_TITULO_HOME = 'div.p-title h2'
SELETOR_RESUMO_HOME = 'div.p-description'
SELETOR_IMAGEM_HOME = 'div.p-img img'

# --- SELETOR DA PÁGINA INTERNA ---
SELETOR_DATA_INTERNA = 'span.sng-data'
# --- FIM DAS CONFIGURAÇÕES ---

def gerar_feed_completo():
    print(f"Iniciando scraper com UNDETECTED CHROMEDRIVER para: {URL_ALVO}")
    
    artigos_coletados = []
    driver = None

    try:
        # --- ETAPA 1: Coletar informações básicas da página principal ---
        print("Configurando o navegador indetectável para o ambiente da Action...")
        options = uc.ChromeOptions()
        
        # Ativa o modo headless e adiciona opções para estabilidade e disfarce
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36')
        options.add_argument("--window-size=1920,1080")

        driver = uc.Chrome(options=options, use_subprocess=True)

        print(f"Acessando página principal: {URL_ALVO}")
        driver.get(URL_ALVO)

        # Espera de forma inteligente até que o container dos artigos esteja visível (máximo 30 segundos)
        print("Aguardando o container de artigos carregar...")
        wait = WebDriverWait(driver, 30) 
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, SELETOR_CONTAINER_ARTIGOS)))
        print("Container de artigos carregado com sucesso!")
        
        # Um pequeno sleep extra pode ajudar com elementos que carregam após o container
        time.sleep(3)

        html_principal = driver.page_source
        soup_principal = BeautifulSoup(html_principal, 'lxml')
        
        container_artigos = soup_principal.select_one(SELETOR_CONTAINER_ARTIGOS)
        if not container_artigos:
            with open('debug_page_error.html', 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            raise Exception(f"Container principal de artigos não encontrado: '{SELETOR_CONTAINER_ARTIGOS}'. Página salva em debug_page_error.html")

        lista_artigos_home = container_artigos.select(SELETOR_ITEM_ARTIGO)
        
        if not lista_artigos_home:
            print("AVISO: Nenhum artigo foi encontrado na página. O site pode ter bloqueado o acesso.")
            print("Salvando screenshot e HTML para depuração...")
            driver.save_screenshot('debug_screenshot.png')
            with open('debug_page.html', 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            print("Arquivos de depuração salvos. O feed será gerado vazio.")
        else:
            print(f"Sucesso! {len(lista_artigos_home)} artigos encontrados na página principal.")

        for artigo_home in lista_artigos_home:
            link_absoluto = urljoin(URL_BASE, artigo_home.get('href', ''))
            titulo_tag = artigo_home.select_one(SELETOR_TITULO_HOME)
            descricao_tag = artigo_home.select_one(SELETOR_RESUMO_HOME)

            if not (link_absoluto and titulo_tag and descricao_tag):
                continue
            
            titulo = titulo_tag.get_text(strip=True)
            descricao = descricao_tag.get_text(strip=True)
            
            imagem_url = None
            imagem_tag = artigo_home.select_one(SELETOR_IMAGEM_HOME)
            if imagem_tag:
                imagem_url = imagem_tag.get('data-lazy-src') or imagem_tag.get('src')
                if imagem_url and not imagem_url.startswith('http'):
                    imagem_url = urljoin(URL_BASE, imagem_url)
            
            artigos_coletados.append({
                'link': link_absoluto,
                'titulo': titulo,
                'descricao': descricao,
                'imagem_url': imagem_url,
                'pubDate': None
            })

        # --- ETAPA 2: Visitar cada artigo para buscar a data correta ---
        if artigos_coletados:
            print("\n--- Iniciando busca das datas de publicação individuais ---")
            fuso_horario_sp = pytz.timezone('America/Sao_Paulo')

            for i, artigo in enumerate(artigos_coletados):
                try:
                    print(f"  - {i+1}/{len(artigos_coletados)}: Visitando '{artigo['titulo']}'...")
                    driver.get(artigo['link'])
                    
                    # Espera pela tag da data na página interna
                    wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, SELETOR_DATA_INTERNA)))
                    time.sleep(1) # Pequena pausa pós-carregamento
                    
                    html_artigo = driver.page_source
                    soup_artigo = BeautifulSoup(html_artigo, 'lxml')
                    
                    data_tag = soup_artigo.select_one(SELETOR_DATA_INTERNA)
                    if data_tag:
                        texto_completo = data_tag.get_text(strip=True)
                        match = re.search(r'(\d{2}/\d{2}/\d{4})\s*(\d{2}h\d{2})', texto_completo)
                        
                        if match:
                            data_str = f"{match.group(1)} {match.group(2)}"
                            data_string_limpa = data_str.replace('h', ':')
                            formato_data = "%d/%m/%Y %H:%M"
                            
                            data_naive = datetime.datetime.strptime(data_string_limpa, formato_data)
                            artigo['pubDate'] = fuso_horario_sp.localize(data_naive)
                            print(f"      -> Data encontrada: {data_str}")
                        else:
                            print(f"      -> AVISO: Padrão de data não encontrado no texto: '{texto_completo}'")
                            artigo['pubDate'] = fuso_horario_sp.localize(datetime.datetime(1970, 1, 1))
                    else:
                        print("      -> AVISO: Tag de data não encontrada.")
                        artigo['pubDate'] = fuso_horario_sp.localize(datetime.datetime(1970, 1, 1))

                except Exception as e:
                    print(f"      -> ERRO ao processar data para {artigo['link']}: {e}")
                    artigo['pubDate'] = fuso_horario_sp.localize(datetime.datetime(1970, 1, 1))
                    continue

    except Exception as e:
        print(f"\nERRO GERAL DURANTE A EXECUÇÃO: {e}")
    finally:
        if driver:
            print("\nFechando o navegador...")
            try:
                driver.quit()
            except Exception as e:
                print(f"Erro ignorado ao fechar o driver: {e}")
    
    # Se não houver artigos, não continue para a ordenação e geração do feed
    if not artigos_coletados:
        print("\nNenhum artigo foi coletado. O processo será encerrado sem gerar o feed.")
        # Cria um feed vazio para não quebrar o workflow, se necessário
        fg = FeedGenerator()
        fg.title(FEED_TITULO)
        fg.link(href=URL_BASE, rel='alternate')
        fg.description(FEED_DESCRICAO)
        fg.rss_file(NOME_ARQUIVO_RSS, pretty=True)
        return

    # --- ORDENAÇÃO MANUAL ANTES DE GERAR O FEED ---
    print("\nOrdenando artigos por data de publicação...")
    artigos_coletados.sort(key=lambda x: x['pubDate'], reverse=True)
    
    print("\nOrdem dos artigos após classificação (mais recente primeiro):")
    for i, artigo in enumerate(artigos_coletados):
        print(f"  {i+1}. {artigo['pubDate'].strftime('%d/%m/%Y %H:%M')} - {artigo['titulo']}")

    # --- ETAPA 3: Gerar o arquivo XML ---
    print("\n--- Gerando o arquivo feed_olhardigital.xml ---")
    fg = FeedGenerator()
    fg.title(FEED_TITULO)
    fg.link(href=URL_BASE, rel='alternate')
    fg.description(FEED_DESCRICAO)
    fg.language('pt-BR')

    print("Adicionando artigos ao feed...")
    for artigo in artigos_coletados:
        fe = fg.add_entry(order='append') # Usar order='append' para manter a ordem
        fe.id(artigo['link'])
        fe.title(artigo['titulo'])
        fe.link(href=artigo['link'])
        fe.description(artigo['descricao'])
        fe.pubDate(artigo['pubDate'])
        
        if artigo['imagem_url']:
            fe.enclosure(url=artigo['imagem_url'], length='0', type='image/jpeg')

    fg.lastBuildDate(datetime.datetime.now(pytz.timezone('America/Sao_Paulo')))
    fg.rss_file(NOME_ARQUIVO_RSS, pretty=True)
    
    print(f"\nSUCESSO! Feed RSS gerado com {len(fg.entry())} artigos e salvo como '{NOME_ARQUIVO_RSS}'.")
    print("Verificação: O XML deve conter os artigos mais recentes no topo.")


if __name__ == "__main__":
    gerar_feed_completo()