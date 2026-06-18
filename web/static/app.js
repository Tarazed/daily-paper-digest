(function () {
  var h = React.createElement;
  var MARKS_KEY = "daily-paper-marks-v1";
  var AB_LABELS = { yes: "有线上 A/B", no: "无线上 A/B", unknown: "未说明" };
  var AB_FILTER_LABELS = Object.assign({ All: "全部 A/B 状态" }, AB_LABELS);

  function App() {
    var state = React.useState(null);
    var payload = state[0];
    var setPayload = state[1];
    var queryState = React.useState("");
    var query = queryState[0];
    var setQuery = queryState[1];
    var archiveMonthState = React.useState("All");
    var archiveMonth = archiveMonthState[0];
    var setArchiveMonth = archiveMonthState[1];
    var archiveDateState = React.useState("All");
    var archiveDate = archiveDateState[0];
    var setArchiveDate = archiveDateState[1];
    var tagState = React.useState("All");
    var tag = tagState[0];
    var setTag = tagState[1];
    var venueState = React.useState("All");
    var venue = venueState[0];
    var setVenue = venueState[1];
    var markFilterState = React.useState("All");
    var importanceFilter = markFilterState[0];
    var setImportanceFilter = markFilterState[1];
    var abFilterState = React.useState("All");
    var abFilter = abFilterState[0];
    var setAbFilter = abFilterState[1];
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
    var archiveMonths = React.useMemo(
      function () {
        return uniqueDesc(
          papers
            .map(function (paper) { return paperMonth(paper); })
            .filter(Boolean)
        );
      },
      [papers]
    );
    var archiveDates = React.useMemo(
      function () {
        return uniqueDesc(
          papers
            .map(function (paper) { return paperDate(paper); })
            .filter(Boolean)
        );
      },
      [papers]
    );
    var archiveMonthLabels = React.useMemo(
      function () {
        return optionLabels(archiveMonths, formatArchiveMonth, "全部月份");
      },
      [archiveMonths]
    );
    var archiveDateLabels = React.useMemo(
      function () {
        return optionLabels(archiveDates, formatArchiveDate, "全部日期");
      },
      [archiveDates]
    );
    var keywordCloud = React.useMemo(
      function () {
        return buildKeywordCloud(papers, ((payload && payload.interests) || {}).include_keywords || []);
      },
      [papers, payload]
    );
    var filtered = React.useMemo(
      function () {
        var needle = query.trim().toLowerCase();
        return papers.filter(function (paper) {
          var haystack = [
            paper.title,
            (paper.authors || []).join(" "),
            displayAffiliations(paper).join(" "),
            (paper.affiliations || []).join(" "),
            paper.generated_summary,
            paper.venue,
            (paper.tags || []).join(" ")
          ]
            .join(" ")
            .toLowerCase();
          return (
            (!needle || haystack.indexOf(needle) >= 0) &&
            (archiveMonth === "All" || paperMonth(paper) === archiveMonth) &&
            (archiveDate === "All" || paperDate(paper) === archiveDate) &&
            (tag === "All" || (paper.tags || []).indexOf(tag) >= 0) &&
            (venue === "All" || displayVenue(paper) === venue) &&
            (importanceFilter === "All" || paper.localMark === importanceFilter) &&
            (abFilter === "All" || (paper.ab_test || "unknown") === abFilter)
          );
        });
      },
      [papers, query, archiveMonth, archiveDate, tag, venue, importanceFilter, abFilter]
    );
    var groupedPapers = React.useMemo(
      function () {
        return groupPapersByMonth(filtered);
      },
      [filtered]
    );

    var stats = buildStats(papers);
    var site = (payload && payload.site) || {};
    var cache = (payload && payload.analysis_cache) || {};

    function setMark(paperId, value) {
      setMarks(function (current) {
        var next = Object.assign({}, current);
        next[paperId] = value;
        return next;
      });
    }

    function selectKeyword(item) {
      var matchingTag = tags.find(function (value) {
        return value.toLowerCase() === item.label.toLowerCase();
      });
      if (matchingTag) {
        setTag(tag === matchingTag ? "All" : matchingTag);
        return;
      }
      setQuery(query.trim().toLowerCase() === item.label.toLowerCase() ? "" : item.label);
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
        h(Stat, { label: "Archive Months", value: archiveMonths.length }),
        h(Stat, { label: "Important", value: stats.important }),
        h(Stat, { label: "A/B Evidence", value: stats.abTests }),
        h(Stat, { label: "Analysis Cache", value: (cache.reused || 0) + "/" + ((cache.reused || 0) + (cache.analyzed || 0)) })
      ),
      h(WordCloud, { items: keywordCloud, activeTag: tag, activeQuery: query, onSelect: selectKeyword }),
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
        h(FilterGroup, { label: "月份", value: archiveMonth, onChange: setArchiveMonth, options: ["All"].concat(archiveMonths), optionLabels: archiveMonthLabels }),
        h(FilterGroup, { label: "日期", value: archiveDate, onChange: setArchiveDate, options: ["All"].concat(archiveDates), optionLabels: archiveDateLabels }),
        h(FilterGroup, { label: "标签", value: tag, onChange: setTag, options: ["All"].concat(tags) }),
        h(FilterGroup, { label: "会议", value: venue, onChange: setVenue, options: ["All"].concat(venues) }),
        h(FilterGroup, {
          label: "A/B 实验",
          value: abFilter,
          onChange: setAbFilter,
          options: ["All", "yes", "no", "unknown"],
          optionLabels: AB_FILTER_LABELS
        }),
        h(FilterGroup, {
          label: "重要性",
          value: importanceFilter,
          onChange: setImportanceFilter,
          options: ["All", "high", "saved", "read", "normal"]
        })
      ),
      h(
        "section",
        { className: "archiveSummary" },
        h(
          "span",
          null,
          (archiveMonth === "All" ? "全部月份" : formatArchiveMonth(archiveMonth)) +
            " · " +
            (archiveDate === "All" ? "全部日期" : formatArchiveDate(archiveDate)) +
            " · " +
            (AB_FILTER_LABELS[abFilter] || AB_FILTER_LABELS.All)
        ),
        h("strong", null, filtered.length + " 篇论文")
      ),
      h(
        "section",
        { className: "archiveList" },
        filtered.length
          ? groupedPapers.map(function (group) {
              return h(
                "section",
                { className: "archiveSection", key: group.month },
                h(
                  "div",
                  { className: "archiveSectionHeader" },
                  h("h2", null, formatArchiveMonth(group.month)),
                  h("span", null, group.papers.length + " 篇")
                ),
                h(
                  "div",
                  { className: "dateGroupList" },
                  group.dateGroups.map(function (dateGroup) {
                    return h(
                      "section",
                      { className: "dateGroup", key: dateGroup.date },
                      h(
                        "div",
                        { className: "dateGroupHeader" },
                        h("span", null, formatDateWithinMonth(dateGroup.date, group.month)),
                        h("strong", null, dateGroup.papers.length + " 篇")
                      ),
                      h(
                        "div",
                        { className: "paperGrid" },
                        dateGroup.papers.map(function (paper) {
                          return h(PaperCard, { key: paper.id, paper: paper, onMark: setMark });
                        })
                      )
                    );
                  })
                )
              );
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
      h("p", { className: "affiliations" }, compactList(displayAffiliations(paper), 4) || "Unknown affiliation"),
      h(
        "div",
        { className: "paperMeta" },
        h("span", null, displayVenue(paper) || paper.status),
        h("span", null, formatPaperDate(paper)),
        h("span", null, paper.analysis_basis === "full_text" ? "全文分析" : "元数据分析")
      ),
      h("div", { className: "statusLine" }, h("span", null, markLabel(mark))),
      h(PreferenceScore, { paper: paper }),
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

  function WordCloud(props) {
    var items = props.items || [];
    if (!items.length) return null;
    var topCount = (items[0] && items[0].count) || 0;
    return h(
      "section",
      { className: "keywordCloud", "aria-label": "Keyword cloud" },
      h(
        "div",
        { className: "keywordCloudHeader" },
        h("h2", null, "关键词词云"),
        h("span", null, items.length + " 个关键词 · 最高 " + topCount + " 篇")
      ),
      h(
        "div",
        { className: "cloudTerms" },
        items.map(function (item) {
          var active =
            props.activeTag.toLowerCase() === item.label.toLowerCase() ||
            props.activeQuery.trim().toLowerCase() === item.label.toLowerCase();
          return h(
            "button",
            {
              className: "cloudTerm cloudLevel-" + item.level + (active ? " active" : ""),
              key: item.label,
              onClick: function () { return props.onSelect(item); },
              title: item.count + " 篇论文"
            },
            item.label,
            h("span", null, item.count)
          );
        })
      )
    );
  }

  function PreferenceScore(props) {
    var paper = props.paper;
    var score = Number(paper.llm_score || 0);
    var signals = Array.isArray(paper.preference_signals) ? paper.preference_signals.filter(Boolean) : [];
    var rationale = String(paper.llm_score_rationale || "").trim();
    if (!score && !signals.length && !rationale) return null;
    return h(
      "div",
      { className: "preferenceScore" },
      h(
        "div",
        { className: "preferenceHead" },
        h("span", null, "偏好评分"),
        h("strong", null, score || "N/A")
      ),
      signals.length
        ? h(
            "div",
            { className: "signalRow" },
            signals.map(function (signal) {
              return h("span", { key: signal }, signal);
            })
          )
        : null,
      rationale ? h("p", null, rationale) : null
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
    var optionLabels = props.optionLabels || {};
    return h(
      "label",
      { className: "filterGroup" },
      h("span", null, props.label),
      h(
        "select",
        {
          "aria-label": props.label,
          value: props.value,
          onChange: function (event) { return props.onChange(event.target.value); }
        },
        props.options.map(function (option) {
          return h("option", { key: option, value: option }, optionLabels[option] || option);
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

  function buildKeywordCloud(papers, includeKeywords) {
    var counts = {};
    var labels = {};

    papers.forEach(function (paper) {
      var text = [
        paper.title,
        paper.abstract,
        paper.generated_summary,
        paper.core_method,
        (paper.tags || []).join(" ")
      ]
        .join(" ")
        .toLowerCase();
      var seen = {};
      (paper.tags || []).forEach(function (value) {
        addKeyword(value, seen, labels);
      });
      (includeKeywords || []).forEach(function (value) {
        if (value && text.indexOf(String(value).toLowerCase()) >= 0) addKeyword(value, seen, labels);
      });
      Object.keys(seen).forEach(function (key) {
        counts[key] = (counts[key] || 0) + 1;
      });
    });

    var values = Object.keys(counts)
      .map(function (key) {
        return { label: labels[key], count: counts[key] };
      })
      .sort(function (left, right) {
        return right.count - left.count || left.label.localeCompare(right.label);
      })
      .slice(0, 36);
    var max = Math.max.apply(null, values.map(function (item) { return item.count; }).concat([0]));
    var min = Math.min.apply(null, values.map(function (item) { return item.count; }).concat([max]));
    return values.map(function (item) {
      var ratio = max === min ? 1 : (item.count - min) / (max - min);
      return Object.assign({}, item, {
        level: Math.max(1, Math.min(5, Math.round(ratio * 4) + 1))
      });
    });
  }

  function addKeyword(value, seen, labels) {
    var label = String(value || "").replace(/\s+/g, " ").trim();
    if (!label || label.length > 48) return;
    var key = label.toLowerCase();
    if (!key || seen[key]) return;
    seen[key] = true;
    if (!labels[key]) labels[key] = label;
  }

  function groupPapersByMonth(papers) {
    var groups = {};
    papers.forEach(function (paper) {
      var month = paperMonth(paper) || "Unknown";
      var date = paperDate(paper) || "Unknown";
      if (!groups[month]) groups[month] = { papers: [], dates: {} };
      groups[month].papers.push(paper);
      if (!groups[month].dates[date]) groups[month].dates[date] = [];
      groups[month].dates[date].push(paper);
    });
    return Object.keys(groups)
      .sort(compareArchiveKeys)
      .map(function (month) {
        return {
          month: month,
          papers: groups[month].papers,
          dateGroups: Object.keys(groups[month].dates)
            .sort(compareArchiveKeys)
            .map(function (date) {
              return { date: date, papers: groups[month].dates[date] };
            })
        };
      });
  }

  function paperDate(paper) {
    return paperDateParts(paper).date;
  }

  function paperMonth(paper) {
    return paperDateParts(paper).month;
  }

  function paperDateParts(paper) {
    var candidates = [paper.published_date, paper.published];
    var ranks = { year: 1, month: 2, day: 3 };
    return candidates.reduce(function (best, value) {
      var parsed = parseArchiveDate(value);
      if (!parsed) return best;
      if (!best || ranks[parsed.precision] > ranks[best.precision]) return parsed;
      return best;
    }, null) || { date: "", month: "", year: "", precision: "unknown" };
  }

  function parseArchiveDate(value) {
    var match = String(value || "").trim().match(/^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?/);
    if (!match) return null;
    var year = match[1];
    var month = match[2];
    var day = match[3];
    if (month && day) return { year: year, month: year + "-" + month, date: year + "-" + month + "-" + day, precision: "day" };
    if (month) return { year: year, month: year + "-" + month, date: year + "-" + month, precision: "month" };
    return { year: year, month: year, date: year, precision: "year" };
  }

  function compareArchiveKeys(left, right) {
    if (left === "Unknown") return 1;
    if (right === "Unknown") return -1;
    return right.localeCompare(left);
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

  function uniqueDesc(values) {
    return Array.from(new Set(values)).sort(function (a, b) { return b.localeCompare(a); });
  }

  function optionLabels(options, formatter, allLabel) {
    return options.reduce(function (labels, option) {
      labels[option] = formatter(option);
      return labels;
    }, { All: allLabel });
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

  function displayAffiliations(paper) {
    var values = Array.isArray(paper.display_affiliations) && paper.display_affiliations.length
      ? paper.display_affiliations
      : paper.affiliations || [];
    var seen = {};
    return values.filter(function (value) {
      var text = String(value || "").trim();
      var key = text.toLowerCase().replace(/^the\s+/, "").replace(/[^a-z0-9]+/g, "");
      if (!text || !key || key === "unknown" || key === "unknownaffiliation" || seen[key]) return false;
      seen[key] = true;
      return true;
    });
  }

  function formatGeneratedAt(value) {
    if (!value) return "Not generated";
    try {
      return new Date(value).toLocaleString();
    } catch (error) {
      return value;
    }
  }

  function formatArchiveDate(value) {
    if (!value || value === "Unknown") return "未知日期";
    var parsed = parseArchiveDate(value);
    if (!parsed) return value;
    if (parsed.precision === "year") return parsed.year + " 年";
    var month = Number(parsed.month.slice(5, 7));
    if (parsed.precision === "month") return parsed.year + " 年 " + month + " 月";
    var day = Number(parsed.date.slice(8, 10));
    return parsed.year + " 年 " + month + " 月 " + day + " 日";
  }

  function formatArchiveMonth(value) {
    if (!value || value === "Unknown") return "未知月份";
    var parsed = parseArchiveDate(value);
    if (!parsed) return value;
    if (parsed.precision === "year") return parsed.year + " 年 · 月份未标注";
    return parsed.year + " 年 " + Number(parsed.month.slice(5, 7)) + " 月";
  }

  function formatDateWithinMonth(date, month) {
    if (!date || date === "Unknown") return "未知日期";
    if (date === month) return "日期未细分";
    var parsed = parseArchiveDate(date);
    if (!parsed || parsed.precision !== "day") return formatArchiveDate(date);
    return Number(parsed.date.slice(8, 10)) + " 日";
  }

  function formatPaperDate(paper) {
    return formatArchiveDate(paperDate(paper));
  }

  ReactDOM.render(h(App), document.getElementById("root"));
})();
