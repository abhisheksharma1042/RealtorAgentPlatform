import ReactECharts from 'echarts-for-react'
import { useMemo } from 'react'

interface DataPoint {
  period?: string
  median_price?: number
  avg_price?: number
  sales_volume?: number
  avg_days_on_market?: number
  [key: string]: any
}

interface TimeSeriesChartProps {
  data: DataPoint[]
  title?: string
  metric?: string
  zipCode?: string
}

export default function TimeSeriesChart({
  data,
  title,
  metric = 'median_price',
  zipCode,
}: TimeSeriesChartProps) {
  const option = useMemo(() => {
    // Sort by date
    const sortedData = [...data].sort(
      (a, b) => new Date(a.period || '').getTime() - new Date(b.period || '').getTime()
    )

    // Extract dates and values
    const dates = sortedData.map((d) => {
      const date = new Date(d.period || '')
      return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
    })

    const values = sortedData.map((d) => d[metric])

    // Determine metric label
    const metricLabels: Record<string, string> = {
      median_price: 'Median Price',
      avg_price: 'Average Price',
      sales_volume: 'Sales Volume',
      avg_days_on_market: 'Days on Market',
    }

    const metricLabel = metricLabels[metric] || metric

    // Format based on metric type
    const isPrice = metric.includes('price')
    const formatter = isPrice
      ? (value: number) => `$${(value / 1000).toFixed(0)}K`
      : (value: number) => value.toLocaleString()

    return {
      title: {
        text: title || `${metricLabel} Trend${zipCode ? ` - ${zipCode}` : ''}`,
        left: 'center',
        textStyle: {
          fontSize: 16,
          fontWeight: 'normal',
        },
      },
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          const param = params[0]
          const value = isPrice
            ? `$${param.value.toLocaleString()}`
            : param.value.toLocaleString()
          return `${param.name}<br/><strong>${value}</strong>`
        },
      },
      grid: {
        left: '10%',
        right: '10%',
        bottom: '15%',
        top: '15%',
      },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: {
          rotate: 45,
          fontSize: 11,
        },
      },
      yAxis: {
        type: 'value',
        name: metricLabel,
        nameLocation: 'center',
        nameGap: 50,
        axisLabel: {
          formatter,
        },
      },
      series: [
        {
          name: metricLabel,
          type: 'line',
          data: values,
          smooth: true,
          lineStyle: {
            width: 3,
            color: '#3b82f6',
          },
          itemStyle: {
            color: '#3b82f6',
          },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(59, 130, 246, 0.3)' },
                { offset: 1, color: 'rgba(59, 130, 246, 0.05)' },
              ],
            },
          },
        },
      ],
    }
  }, [data, title, metric, zipCode])

  return (
    <div className="w-full">
      <ReactECharts option={option} style={{ height: '400px' }} />
    </div>
  )
}
