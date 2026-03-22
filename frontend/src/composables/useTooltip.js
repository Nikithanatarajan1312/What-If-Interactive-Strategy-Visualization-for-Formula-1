import * as d3 from 'd3'

export function useTooltip() {
  let tip = d3.select('body').select('.tooltip')
  if (tip.empty()) {
    tip = d3.select('body')
      .append('div')
      .attr('class', 'tooltip')
      .attr('role', 'tooltip')
      .attr('aria-hidden', 'true')
      .style('opacity', 0)
  }

  function show(html) {
    tip.html(html)
      .attr('aria-hidden', 'false')
      .transition().duration(100).style('opacity', 1)
  }

  function move(event) {
    const vw = window.innerWidth
    const pageX = event.pageX
    const flipX = pageX > vw - 260

    tip
      .style('left', flipX ? `${pageX - 220}px` : `${pageX + 14}px`)
      .style('top', `${event.pageY - 10}px`)
  }

  function hide() {
    tip
      .attr('aria-hidden', 'true')
      .transition().duration(200).style('opacity', 0)
  }

  return { show, move, hide }
}
