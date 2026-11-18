// 年级→班级两级选择：班级按年级归组，先选年级再选班，避免一锅长列表
// 没填年级的班归到「未填年级」组

// 年级清单（按班级出现顺序去重）
function gradeLabelsOf(classes) {
  const seen = {}
  const out = []
  ;(classes || []).forEach(function (c) {
    const g = c.grade || '未填年级'
    if (!seen[g]) {
      seen[g] = 1
      out.push(g)
    }
  })
  return out
}

// 某年级下的班级
function filterByGrade(classes, grade) {
  return (classes || []).filter(function (c) {
    return (c.grade || '未填年级') === grade
  })
}

module.exports = {
  gradeLabelsOf: gradeLabelsOf,
  filterByGrade: filterByGrade,
}
