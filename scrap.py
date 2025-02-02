import csv
import os
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
import logging
import sys
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Headers for the request
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/58.0.3029.110 Safari/537.3"
    )
}

# Create a session with retry mechanism
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount("http://", HTTPAdapter(max_retries=retries))
session.mount("https://", HTTPAdapter(max_retries=retries))


def read_urls(file_path):
    """Read URLs from the checkpoint file."""
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            return [line.strip() for line in file.readlines() if line.strip()]
    return []


def write_urls(file_path, urls):
    """Write URLs to the checkpoint file."""
    with open(file_path, "w") as file:
        for url in urls:
            file.write(url + "\n")


def generate_urls(file_path, start_landmark_id, process_range):
    """Generate a list of URLs based on the provided landmark IDs and save them."""
    base_url = "https://www.openrice.com/en/hongkong/restaurants?regionId=1&landmarkId={}&tabIndex=0"
    with open(file_path, "w") as file:
        for landmark_id in range(
            int(start_landmark_id), int(start_landmark_id) + int(process_range)
        ):
            url = base_url.format(landmark_id)
            file.write(url + "\n")
    logging.info(f"URLs generated and saved to {file_path}.")


def scrape_openrice(url, data):
    """Scrape restaurant data from a single URL."""
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
    restaurants = soup.find_all("div", class_="poi-list-cell-desktop-container")
    logging.info(f"Found {len(restaurants)} restaurants.")
    for index, restaurant in enumerate(restaurants, start=1):
        logging.info(f"Processing restaurant {index}...")

        # Name extraction
        name = (
            restaurant.find("div", class_="poi-name").get_text(strip=True)
            if restaurant.find("div", class_="poi-name")
            else "N/A"
        )

        # Extract accurate address:
        # The address is in the second <div> within the info section.
        info_section = restaurant.find(
            "section", class_="poi-list-cell-desktop-right-top-info-section"
        )
        if info_section:
            address_divs = info_section.find_all("div", recursive=False)
            if len(address_divs) >= 2:
                address = address_divs[1].get_text(strip=True)
            else:
                address = "N/A"
        else:
            address = "N/A"

        # Food type and pricing extraction:
        # We expect the spans (in order) to be: District, Cuisine Type, Restaurant Type, Price Range.
        info = restaurant.find("div", class_="poi-list-cell-line-info")
        if info:
            spans = info.find_all("span", class_="poi-list-cell-line-info-link")
            district = spans[0].get_text(strip=True) if len(spans) > 0 else "N/A"
            cuisine_type = spans[1].get_text(strip=True) if len(spans) > 1 else "N/A"
            restaurant_type = spans[2].get_text(strip=True) if len(spans) > 2 else "N/A"
            price_range = spans[3].get_text(strip=True) if len(spans) > 3 else "N/A"
        else:
            district = "N/A"
            cuisine_type = "N/A"
            restaurant_type = "N/A"
            price_range = "N/A"

        # Append the district to the address (if not already included)
        if address != "N/A" and district != "N/A" and district not in address:
            address = f"{address}, {district}"

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
        detail_link = restaurant.find(
            "a", class_="poi-list-cell-desktop-right-link-overlay"
        )
        if detail_link and detail_link.get("href"):
            detail_url = "https://www.openrice.com" + detail_link["href"]
        else:
            detail_url = "N/A"

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
                "District": district,
                "Cuisine Type": cuisine_type,
                "Restaurant Type": restaurant_type,
                "Price Range": price_range,
                "Smile Score": smile_score,
                "Cry Score": cry_score,
                "Promotions": promotions,
                "Contact": contact,
                "Opening Hours": opening_hours,
                "URL": detail_url,
            }
        )


def main():
    url_file = "url.txt"
    last_landmark_file = "last_landmark.txt"
    existing_urls = read_urls(url_file)
    generate_new = False
    start_landmark_id = None
    process_range = None

    if existing_urls:
        # A checkpoint is found.
        choice = (
            input(
                "Checkpoint found. Do you want to (R)esume or (G)enerate new URLs? (R/G): "
            )
            .strip()
            .lower()
        )
        if choice == "g":
            generate_new = True
        else:
            logging.info("Resuming from existing checkpoint.")
    else:
        # No checkpoint found.
        if os.path.exists(last_landmark_file):
            with open(last_landmark_file, "r") as f:
                last_landmark = f.read().strip()
            if last_landmark.isdigit():
                start_landmark_id = last_landmark
                logging.info(
                    f"No checkpoint found. Using previous run's ending landmark ID as the start: {start_landmark_id}."
                )
            else:
                start_landmark_id = input("Enter the start landmark ID: ").strip()
        else:
            start_landmark_id = input("Enter the start landmark ID: ").strip()
        process_range = input("Enter the range of landmark IDs: ").strip()
        generate_new = True

    # If generating new URLs, create the checkpoint file and update the last landmark.
    if generate_new:
        generate_urls(url_file, start_landmark_id, process_range)
        # Compute the new ending landmark ID and store it for the next run.
        end_landmark = int(start_landmark_id) + int(process_range)
        with open(last_landmark_file, "w") as f:
            f.write(str(end_landmark))
        existing_urls = read_urls(url_file)

    start_time = time.time()
    logging.info("Scraping started.")
    data = []

    try:
        # Process URLs one by one; update the checkpoint file after each URL.
        for idx, url in enumerate(existing_urls):
            logging.info(f"Processing URL ({idx + 1}/{len(existing_urls)}): {url}")
            scrape_openrice(url, data)
            # Save remaining URLs to the checkpoint file.
            remaining_urls = existing_urls[idx + 1 :]
            write_urls(url_file, remaining_urls)
    except KeyboardInterrupt:
        logging.info("Scraper paused by user (KeyboardInterrupt). Checkpoint saved.")
        sys.exit(0)  # Exit gracefully

    # Write data to CSV if any data was collected.
    if data:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_dir = "./output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        # The CSV filename uses the starting landmark id (from this generation)
        csv_file = os.path.join(
            output_dir, f"restaurants_{start_landmark_id}_{timestamp}.csv"
        )
        with open(csv_file, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "Name",
                    "Address",
                    "District",
                    "Cuisine Type",
                    "Restaurant Type",
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
    main()
