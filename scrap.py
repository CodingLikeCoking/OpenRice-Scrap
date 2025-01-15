import csv
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
import logging
import sys
import select  # Import added for handling user input during runtime
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Headers for the request
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
}

# Create a session with retry mechanism
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount("http://", HTTPAdapter(max_retries=retries))
session.mount("https://", HTTPAdapter(max_retries=retries))


# Function to read URLs from a file
def read_urls(file_path):
    with open(file_path, "r") as file:
        return [line.strip() for line in file.readlines()]


# Function to write URLs to a file
def write_urls(file_path, urls):
    with open(file_path, "w") as file:
        for url in urls:
            file.write(url + "\n")


# Function to generate URLs and write them to a file
def generate_urls(file_path):
    base_url = "https://www.openrice.com/en/hongkong/restaurants?regionId=1&landmarkId={}&tabIndex=0"

    with open(file_path, "w") as file:
        for landmark_id in range(35281, 35300):  # Adjust landmark ID range as necessary
            url = base_url.format(landmark_id)
            file.write(url + "\n")
    logging.info(f"URLs generated and saved to {file_path}.")


# Function to scrape a single URL
def scrape_openrice(url, data):
    logging.info(f"Fetching URL: {url}")
    try:
        response = session.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            logging.warning(
                f"Failed to retrieve page. Status code: {response.status_code}"
            )
            return
        logging.info("Successfully fetched URL.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching URL {url}: {e}")
        return

    soup = BeautifulSoup(response.text, "html.parser")

    # Extract restaurant details
    restaurants = soup.find_all("div", class_="poi-list-cell-desktop-container")
    logging.info(f"Found {len(restaurants)} restaurants.")
    for index, restaurant in enumerate(restaurants, start=1):
        logging.info(f"Processing restaurant {index}...")

        name = (
            restaurant.find("div", class_="poi-name").get_text(strip=True)
            if restaurant.find("div", class_="poi-name")
            else "N/A"
        )
        address = (
            restaurant.find(
                "div", class_="poi-list-cell-desktop-right-top-wrapper-main"
            )
            .find_next("div")
            .get_text(strip=True)
        )

        # Food type and pricing
        info = restaurant.find("div", class_="poi-list-cell-line-info")
        food_types = (
            " / ".join(
                [
                    item.get_text(strip=True)
                    for item in info.find_all(
                        "span", class_="poi-list-cell-line-info-link"
                    )
                ]
            )
            if info
            else "N/A"
        )
        price_range = (
            info.find_all("span", class_="poi-list-cell-line-info-link")[-1].get_text(
                strip=True
            )
            if info
            else "N/A"
        )

        # Ratings/Reviews
        smile_score = (
            restaurant.find("div", class_="smile").get_text(strip=True)
            if restaurant.find("div", class_="smile")
            else "0"
        )
        cry_score = (
            restaurant.find("div", class_="cry").get_text(strip=True)
            if restaurant.find("div", class_="cry")
            else "0"
        )

        # Promotions
        promotions = (
            ", ".join([promo["alt"] for promo in restaurant.find_all("img", alt=True)])
            if restaurant.find_all("img", alt=True)
            else "N/A"
        )

        # Link to restaurant detail page
        detail_url = (
            "https://www.openrice.com"
            + restaurant.find("a", class_="poi-list-cell-desktop-right-link-overlay")[
                "href"
            ]
        )
        contact = "N/A"
        opening_hours = "N/A"

        # Fetch restaurant detail page for contact info and opening hours
        try:
            detail_response = session.get(detail_url, headers=headers, timeout=10)
            if detail_response.status_code == 200:
                detail_soup = BeautifulSoup(detail_response.text, "html.parser")
                phone_section = detail_soup.find("section", class_="telephone-section")
                contact = (
                    phone_section.find("div", class_="content").get_text(strip=True)
                    if phone_section
                    else "N/A"
                )

                opening_hours_section = detail_soup.find(
                    "div", class_="opening-hours-list"
                )
                opening_hours = (
                    opening_hours_section.find(
                        "div", class_="opening-hours-time"
                    ).get_text(strip=True)
                    if opening_hours_section
                    else "N/A"
                )
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching detail page {detail_url}: {e}")

        data.append(
            {
                "Name": name,
                "Address": address,
                "Food Type": food_types,
                "Price Range": price_range,
                "Smile Score": smile_score,
                "Cry Score": cry_score,
                "Promotions": promotions,
                "Contact": contact,
                "Opening Hours": opening_hours,
                "URL": detail_url,
            }
        )


# Main function to handle URL generation and scraping
def main(generate_new_urls=False):
    url_file = "url.txt"

    if generate_new_urls:
        generate_urls(url_file)

    start_time = time.time()
    logging.info("Scraping started.")

    data = []
    remaining_urls = read_urls(url_file)
    processed_urls = []

    for url in remaining_urls:
        print(f"About to fetch: {url}. Type 's' within 2 seconds to stop.")
        time.sleep(2)

        if sys.stdin in select.select([sys.stdin], [], [], 2)[0]:
            user_input = sys.stdin.readline().strip()
            if user_input.lower() == "s":
                logging.info(f"Stopping scraping at {url} as requested by the user.")
                break

        scrape_openrice(url, data)
        processed_urls.append(url)

    # Update URL file by removing processed URLs
    remaining_urls = [url for url in remaining_urls if url not in processed_urls]
    write_urls(url_file, remaining_urls)

    # Generate a file name with date-time information
    if data:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        csv_file = f"restaurants_{timestamp}.csv"

        # Write data to a CSV file
        with open(csv_file, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "Name",
                    "Address",
                    "Food Type",
                    "Price Range",
                    "Smile Score",
                    "Cry Score",
                    "Promotions",
                    "Contact",
                    "Opening Hours",
                    "URL",
                ],
            )
            writer.writeheader()
            writer.writerows(data)

        logging.info(f"Data successfully written to {csv_file}")

    elapsed_time = time.time() - start_time
    logging.info(f"Total elapsed time: {elapsed_time} seconds")
    print(f"Total elapsed time: {elapsed_time} seconds")


if __name__ == "__main__":
    main(generate_new_urls=True)
