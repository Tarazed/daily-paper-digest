from daily_paper.arxiv import parse_feed


SAMPLE_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2606.01234v2</id>
    <updated>2026-06-07T10:00:00Z</updated>
    <published>2026-06-06T09:00:00Z</published>
    <title>LLM4Rec: Large Language Models for Recommendation</title>
    <summary>We study large language model recommendation for sequential recommendation tasks.</summary>
    <author>
      <name>Alice Zhang</name>
      <arxiv:affiliation>Stanford University</arxiv:affiliation>
    </author>
    <author>
      <name>Bob Lee</name>
      <arxiv:affiliation>Google DeepMind</arxiv:affiliation>
    </author>
    <arxiv:primary_category term="cs.IR"/>
    <category term="cs.IR"/>
    <category term="cs.CL"/>
    <link href="http://arxiv.org/abs/2606.01234v2" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2606.01234v2" rel="related" type="application/pdf"/>
  </entry>
</feed>
"""


def test_parse_feed_extracts_required_fields():
    papers = parse_feed(SAMPLE_FEED)

    assert len(papers) == 1
    paper = papers[0]
    assert paper.id == "arxiv:2606.01234"
    assert paper.title == "LLM4Rec: Large Language Models for Recommendation"
    assert paper.authors == ["Alice Zhang", "Bob Lee"]
    assert paper.affiliations == ["Stanford University", "Google DeepMind"]
    assert paper.primary_category == "cs.IR"
    assert paper.pdf_url == "http://arxiv.org/pdf/2606.01234v2"
