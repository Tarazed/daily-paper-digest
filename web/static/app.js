(function () {
  var h = React.createElement;
  var MARKS_KEY = "daily-paper-marks-v1";
  var AB_LABELS = { yes: "有线上 A/B", no: "无线上 A/B", unknown: "未说明" };

  function App() {
    var state = React.useState(null);
    var payload = state[0];
    var setPayload = state[1];
    var queryState = React.useState("");
    var query = queryState[0];
    var setQuery = queryState[1];
    var tagState = React.useState("All");
    var tag = tagState[0];
    var setTag = tagState[1];
    var venueState = React.useState("All");
    var venue = venueState[0];
    var setVenue = venueState[1];
    var markFilterState = React.useState("All");
    var importanceFilter = markFilterState[0];
    var setImportanceFilter = markFilterState[1];
    var marksState = React.useState(loadMarks);
    var marks = marksState[0];
    var setMarks = marksState[1];

    React.useEffect(function () {
      fetch("./papers.json")
        .then(function (response) {
          return response.json();
        })
        .then(setPayload)
        .catch(function () {
          setPayload({ papers: [], site: { title: "Daily Paper Digest" } });
        });
    }, []);

    React.useEffect(
      function () {
        window.localStorage.setItem(MARKS_KEY, JSON.stringify(marks));
      },
      [marks]
    );

    var papers = React.useMemo(
      function () {
        return ((payload && payload.papers) || []).map(function (paper) {
          return Object.assign({}, paper, {
            localMark: marks[paper.id] || paper.importance || "normal"
          });
        });
      },
      [payload, marks]
    );

    var tags = React.useMemo(
      function () {
        return unique(flatten(papers.map(function (paper) { return paper.tags || []; })));
      },
      [papers]
    );
    var venues = React.useMemo(
      function () {
        return unique(
          papers
            .map(function (paper) { return displayVenue(paper); })
            .filter(Boolean)
        );
      },
      [papers]
    );
    var filtered = React.useMemo(
      function () {
        var needle = query.trim().toLowerCase();
        return papers.filter(function (paper) {
          var haystack = [
            paper.title,
            (paper.authors || []).join(" "),
            (paper.affiliations || []).join(" "),
            paper.generated_summary,
            paper.venue,
            (paper.tags || []).join(" ")
          ]
            .join(" ")
            .toLowerCase();
          return (
            (!needle || haystack.indexOf(needle) >= 0) &&
            (tag === "All" || (paper.tags || []).indexOf(tag) >= 0) &&
            (venue === "All" || displayVenue(paper) === venue) &&
            (importanceFilter === "All" || paper.localMark === importanceFilter)
          );
        });
      },
      [papers, query, tag, venue, importanceFilter]
    );

    var stats = buildStats(papers);
    var site = (payload && payload.site) || {};

    function setMark(paperId, value) {
      setMarks(function (current) {
        var next = Object.assign({}, current);
        next[paperId] = value;
        return next;
      });
    }

    return h(
      "main",
      { className: "shell" },
      h(
        "header",
        { className: "topbar" },
        h(
          "div",
          null,
          h("div", { className: "eyebrow" }, "GitHub Pages Research Dashboard"),
          h("h1", null, site.title || "Daily Paper Digest"),
          h("p", null, site.subtitle || "Recommendation Systems Paper Digest")
        ),
        h(
          "div",
          { className: "metaBlock" },
          h("span", null, "Updated"),
          h("strong", null, formatGeneratedAt(payload && payload.generated_at))
        )
      ),
      h(
        "section",
        { className: "statsGrid", "aria-label": "Digest statistics" },
        h(Stat, { label: "Papers", value: stats.total }),
        h(Stat, { label: "Important", value: stats.important }),
        h(Stat, { label: "A/B Evidence", value: stats.abTests }),
        h(Stat, { label: "Top Venues", value: stats.venues })
      ),
      payload && payload.analysis_enabled === false
        ? h(
            "div",
            { className: "notice" },
            "未检测到 DEEPSEEK_API_KEY，创新点、实验结果和 A/B 测试字段使用保守 fallback。本机构建请设置 .env.local 后重新运行 ./scripts/build_pages.sh；GitHub Actions 部署请添加同名 Repository Secret 后重新运行 workflow。"
          )
        : null,
      h(
        "section",
        { className: "toolbar" },
        h("input", {
          className: "searchInput",
          value: query,
          onChange: function (event) { return setQuery(event.target.value); },
          placeholder: "搜索标题、作者、机构、标签..."
        }),
        h(FilterGroup, { label: "标签", value: tag, onChange: setTag, options: ["All"].concat(tags) }),
        h(FilterGroup, { label: "会议", value: venue, onChange: setVenue, options: ["All"].concat(venues) }),
        h(FilterGroup, {
          label: "重要性",
          value: importanceFilter,
          onChange: setImportanceFilter,
          options: ["All", "high", "saved", "read", "normal"]
        })
      ),
      h(
        "section",
        { className: "paperGrid" },
        filtered.length
          ? filtered.map(function (paper) {
              return h(PaperCard, { key: paper.id, paper: paper, onMark: setMark });
            })
          : h("div", { className: "emptyState" }, "没有匹配的论文。调整搜索或筛选条件。")
      )
    );
  }

  function PaperCard(props) {
    var paper = props.paper;
    var mark = paper.localMark || "normal";
    return h(
      "article",
      { className: "paperCard mark-" + mark },
      h(
        "div",
        { className: "cardHeader" },
        h(
          "div",
          { className: "tagRow" },
          mark === "high" ? h("span", { className: "badge badgeImportant" }, "重要") : null,
          (paper.tags || []).slice(0, 5).map(function (item) {
            return h("span", { className: "badge", key: item }, item);
          })
        ),
        h(
          "div",
          { className: "markControls", "aria-label": "Importance controls" },
          h(
            "button",
            { className: mark === "high" ? "active" : "", title: "标记重要", onClick: function () { return props.onMark(paper.id, mark === "high" ? "normal" : "high"); } },
            "☆"
          ),
          h(
            "button",
            { className: mark === "saved" ? "active" : "", title: "保存稍后阅读", onClick: function () { return props.onMark(paper.id, mark === "saved" ? "normal" : "saved"); } },
            "⌑"
          ),
          h(
            "button",
            { className: mark === "read" ? "active" : "", title: "标记已读", onClick: function () { return props.onMark(paper.id, mark === "read" ? "normal" : "read"); } },
            "✓"
          )
        )
      ),
      h("h2", null, paper.title),
      h("p", { className: "authors" }, compactList(paper.authors, 8) || "Unknown authors"),
      h("p", { className: "affiliations" }, compactList(paper.affiliations, 4) || "Unknown affiliation"),
      h(
        "div",
        { className: "paperMeta" },
        h("span", null, displayVenue(paper) || paper.status),
        h("span", null, paper.published_date || (paper.published || "").slice(0, 10)),
        h("span", null, paper.analysis_basis === "full_text" ? "全文分析" : "元数据分析")
      ),
      h("div", { className: "statusLine" }, h("span", null, markLabel(mark))),
      h("p", { className: "summary" }, paper.generated_summary || paper.abstract || "No summary available."),
      paper.core_method
        ? h(
            "div",
            { className: "methodLine" },
            h("span", null, "核心方法"),
            h("p", null, paper.core_method)
          )
        : null,
      h(InfoSection, { title: "创新点", items: paper.innovation_points }),
      h(InfoSection, { title: "实验结果", items: paper.experiment_results }),
      h(
        "div",
        { className: "abBox ab-" + (paper.ab_test || "unknown") },
        h("span", null, AB_LABELS[paper.ab_test] || AB_LABELS.unknown),
        h("p", null, paper.ab_test_evidence || "论文未报告线上 A/B 测试。")
      ),
      paper.practical_value
        ? h(
            "div",
            { className: "valueLine" },
            h("span", null, "实践价值"),
            h("p", null, paper.practical_value)
          )
        : null,
      h(
        "div",
        { className: "linkRow" },
        paper.abs_url ? h("a", { href: paper.abs_url, target: "_blank", rel: "noreferrer" }, "Paper") : null,
        paper.pdf_url ? h("a", { href: paper.pdf_url, target: "_blank", rel: "noreferrer" }, "PDF") : null,
        paper.doi ? h("a", { href: "https://doi.org/" + paper.doi, target: "_blank", rel: "noreferrer" }, "DOI") : null
      )
    );
  }

  function InfoSection(props) {
    var values = Array.isArray(props.items) ? props.items.filter(Boolean) : [];
    return h(
      "section",
      { className: "infoSection" },
      h("h3", null, props.title),
      values.length
        ? h(
            "ul",
            null,
            values.map(function (item, index) {
              return h("li", { key: props.title + "-" + index }, item);
            })
          )
        : h("p", null, "暂无明确证据。")
    );
  }

  function Stat(props) {
    return h("div", { className: "statCard" }, h("span", null, props.label), h("strong", null, props.value));
  }

  function FilterGroup(props) {
    return h(
      "label",
      { className: "filterGroup" },
      h("span", null, props.label),
      h(
        "select",
        {
          value: props.value,
          onChange: function (event) { return props.onChange(event.target.value); }
        },
        props.options.map(function (option) {
          return h("option", { key: option, value: option }, option);
        })
      )
    );
  }

  function buildStats(papers) {
    return {
      total: papers.length,
      important: papers.filter(function (paper) {
        return paper.localMark === "high" || paper.importance === "high";
      }).length,
      abTests: papers.filter(function (paper) { return paper.ab_test === "yes"; }).length,
      venues:
        unique(
          papers
            .map(function (paper) { return displayVenue(paper); })
            .filter(Boolean)
        )
          .slice(0, 3)
          .join(" · ") || "N/A"
    };
  }

  function displayVenue(paper) {
    var value = paper.venue_key || paper.venue || "";
    if (Array.isArray(value)) return value[0] || "";
    value = String(value);
    if (value.indexOf("[") === 0) return paper.venue_key || "";
    return value;
  }

  function markLabel(mark) {
    if (mark === "high") return "当前状态：重要";
    if (mark === "saved") return "当前状态：稍后阅读";
    if (mark === "read") return "当前状态：已读";
    return "当前状态：未标记";
  }

  function loadMarks() {
    try {
      return JSON.parse(window.localStorage.getItem(MARKS_KEY) || "{}");
    } catch (error) {
      return {};
    }
  }

  function unique(values) {
    return Array.from(new Set(values)).sort(function (a, b) { return a.localeCompare(b); });
  }

  function flatten(values) {
    return values.reduce(function (acc, item) { return acc.concat(item); }, []);
  }

  function compactList(values, limit) {
    var items = (values || []).filter(Boolean);
    if (!items.length) return "";
    var visible = items.slice(0, limit).join(", ");
    return items.length > limit ? visible + " et al." : visible;
  }

  function formatGeneratedAt(value) {
    if (!value) return "Not generated";
    try {
      return new Date(value).toLocaleString();
    } catch (error) {
      return value;
    }
  }

  ReactDOM.render(h(App), document.getElementById("root"));
})();
