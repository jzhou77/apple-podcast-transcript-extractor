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
                'episode_title': row[0],
                'pub_date': row[1],
                'duration': row[2],
                'podcast_title': row[3],
                'author': row[4],
                'category': row[5]
            }
        return None
    except sqlite3.Error as e:
        print(f"Database query error for {transcript_identifier}: {e}")
        return None
