from datetime import datetime
import os
import sqlite3


def query_episode_metadata(db, transcript_identifier):
    """
    Query episode metadata from the Apple Podcasts database.

    Args:
        db: SQLite database connection
        transcript_identifier: The transcript identifier to look up

    Returns:
        Dictionary with episode metadata or None if not found
    """
    query = """
        SELECT
            e.ZTITLE as episode_title,
            e.ZPUBDATE,
            e.ZDURATION,
            p.ZTITLE as podcast_title,
            p.ZAUTHOR,
            p.ZCATEGORY
        FROM ZMTEPISODE e
        JOIN ZMTPODCAST p ON e.ZPODCASTUUID = p.ZUUID
        WHERE e.ZTRANSCRIPTIDENTIFIER = ?
    """

    try:
        cursor = db.cursor()
        cursor.execute(query, (transcript_identifier,))
        row = cursor.fetchone()

        if row:
            return {
                "episode_title": row[0],
                "pub_date": row[1],
                "duration": row[2],
                "podcast_title": row[3],
                "author": row[4],
                "category": row[5],
            }
        return None
    except sqlite3.Error as e:
        print(f"Database query error for {transcript_identifier}: {e}")
        return None


def query_show_info(db, store_collection_id):
    """
    Query podcast show information from the Apple Podcasts database.

    Args:
        db: SQLite database connection
        store_collection_id: The podcast's store collection ID

    Returns:
        Dictionary with podcast show data or None if not found
    """
    query = """
        SELECT
            p.ZTITLE as podcast_title,
            p.ZAUTHOR as author,
            p.ZCATEGORY as category,
            p.ZUUID as podcast_uuid,
            p.ZSTORECOLLECTIONID as store_collection_id,
            p.Z_PK as primary_key,
            p.ZITEMDESCRIPTION as description
        FROM ZMTPODCAST p
        WHERE p.ZSTORECOLLECTIONID = ?
    """

    try:
        cursor = db.cursor()
        cursor.execute(query, (store_collection_id,))
        row = cursor.fetchone()

        if row:
            return {
                "podcast_title": row[0],
                "author": row[1],
                "category": row[2],
                "podcast_uuid": row[3],
                "store_collection_id": row[4],
                "primary_key": row[5],
                "description": row[6],
            }
        return None
    except sqlite3.Error as e:
        print(f"Database query error for store_collection_id {store_collection_id}: {e}")
        return None


def query_all_episodes_for_show(db, store_collection_id):
    """
    Query all episodes for a podcast show from the Apple Podcasts database.

    Args:
        db: SQLite database connection
        store_collection_id: The podcast's store collection ID

    Returns:
        List of dictionaries with episode data, ordered by publication date (newest first)
    """
    query = """
        SELECT
            e.ZSTORETRACKID as episode_id,
            e.ZTITLE as episode_title,
            e.ZPUBDATE as pub_date,
            e.ZDURATION as duration,
            e.ZTRANSCRIPTIDENTIFIER as transcript_id,
            e.ZUUID as episode_uuid
        FROM ZMTEPISODE e
        JOIN ZMTPODCAST p ON e.ZPODCAST = p.Z_PK
        WHERE p.ZSTORECOLLECTIONID = ?
        ORDER BY e.ZPUBDATE DESC
    """

    try:
        cursor = db.cursor()
        cursor.execute(query, (store_collection_id,))
        rows = cursor.fetchall()

        episodes = []
        for row in rows:
            episodes.append(
                {
                    "episode_id": row[0],
                    "episode_title": row[1],
                    "pub_date": row[2],
                    "duration": row[3],
                    "transcript_id": row[4],
                    "episode_uuid": row[5],
                }
            )

        return episodes
    except sqlite3.Error as e:
        print(
            f"Database query error for store_collection_id {store_collection_id}: {e}"
        )
        return []


if __name__ == "__main__":
    # Example usage
    home_dir = os.path.expanduser("~")
    db_path = os.path.join(
        home_dir,
        "Library/Group Containers/243LU875E5.groups.com.apple.podcasts/Documents/MTLibrary.sqlite",
    )

    db = sqlite3.connect(db_path)

    # Query show information
    show_id = 1483081827
    show = query_show_info(db, show_id)
    if show:
        print(f"Podcast: {show['podcast_title']}")
        print(f"Author: {show['author']}")
        print(f"Category: {show['category']}\n")

    # Query all episodes for the show
    episodes = query_all_episodes_for_show(db, show_id)
    print(f"Found {len(episodes)} episodes:\n")
    for ep in episodes:
        dt = datetime.fromtimestamp(ep["pub_date"] + 978307200)
        print(f'{dt.strftime("%Y-%m-%d")} - {ep["episode_title"]}')

    db.close()
