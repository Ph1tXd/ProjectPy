import requests
from bs4 import BeautifulSoup
import psycopg2
import os

def create_or_update_tables():
    dbname = os.getenv("DB_NAME", "bruno")
    user = os.getenv("DB_USER", "bruno")
    password = os.getenv("DB_PASSWORD", "1234")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    with psycopg2.connect(dbname=dbname, user=user, password=password, host=host, port=port) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS authors (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    bio TEXT NOT NULL,
                    birth TEXT
                );

                CREATE TABLE IF NOT EXISTS quotes (
                    id SERIAL PRIMARY KEY,
                    text TEXT NOT NULL,
                    author_id INTEGER REFERENCES authors(id)
                );
            """)
            
            cur.execute("""
                DO $$ 
                BEGIN
                    IF EXISTS (
                        SELECT 1 
                        FROM information_schema.columns 
                        WHERE table_name='authors' AND column_name='birth_date'
                    ) THEN
                        ALTER TABLE authors DROP COLUMN birth_date;
                    END IF;

                    IF EXISTS (
                        SELECT 1 
                        FROM information_schema.columns 
                        WHERE table_name='authors' AND column_name='additional_info'
                    ) THEN
                        ALTER TABLE authors DROP COLUMN additional_info;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 
                        FROM information_schema.columns 
                        WHERE table_name='authors' AND column_name='birth'
                    ) THEN
                        ALTER TABLE authors ADD COLUMN birth TEXT;
                    END IF;
                END $$;
            """)
        conn.commit()

def save_to_database(quotes, authors):
    dbname = os.getenv("DB_NAME", "bruno")
    user = os.getenv("DB_USER", "bruno")
    password = os.getenv("DB_PASSWORD", "1234")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    with psycopg2.connect(dbname=dbname, user=user, password=password, host=host, port=port) as conn:
        with conn.cursor() as cur:
            author_ids = {}
            for author, details in authors.items():
                bio = details['bio']
                birth = details['birth']
                cur.execute("""
                    INSERT INTO authors (name, bio, birth)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (name) DO UPDATE 
                    SET bio = EXCLUDED.bio, 
                        birth = EXCLUDED.birth
                    RETURNING id;
                """, (author, bio, birth))
                result = cur.fetchone()
                if result:
                    author_ids[author] = result[0]
                else:
                    cur.execute("SELECT id FROM authors WHERE name = %s", (author,))
                    author_ids[author] = cur.fetchone()[0]

            for quote, author in quotes:
                cur.execute("""
                    INSERT INTO quotes (text, author_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING;
                """, (quote, author_ids[author]))
        conn.commit()

def fetch_quotes():
    quotes = []
    authors = {}
    page = 1

    while True:
        url = f"https://quotes.toscrape.com/page/{page}/"
        response = requests.get(url)
        if response.status_code != 200:
            break

        soup = BeautifulSoup(response.text, "html.parser")
        quote_elements = soup.select(".quote")

        if not quote_elements:
            break

        for quote_element in quote_elements:
            text = quote_element.select_one(".text").get_text()
            author = quote_element.select_one(".author").get_text()
            author_url = quote_element.select_one("a")['href']

            if author not in authors:
                bio_response = requests.get(f"https://quotes.toscrape.com{author_url}")
                bio_soup = BeautifulSoup(bio_response.text, "html.parser")
                bio = bio_soup.select_one(".author-description").get_text().strip()
                birth_date = bio_soup.select_one(".author-born-date").get_text().strip()
                birth_location = bio_soup.select_one(".author-born-location").get_text().strip()
                
                birth = f"{birth_date} {birth_location}"

                authors[author] = {
                    'bio': bio,
                    'birth': birth
                }

            quotes.append((text, author))

        page += 1

    return quotes, authors

if __name__ == "__main__":
    create_or_update_tables()
    quotes, authors = fetch_quotes()
    save_to_database(quotes, authors)
    print("Данные сохранены в базу данных.")
