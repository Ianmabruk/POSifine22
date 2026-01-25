# Main Admin Dashboard - Quick Reference Guide

## Accessing the Dashboard

**URL**: `https://your-domain.com/main-admin`

**Requirements**:
- Owner account with `role: 'owner'`
- Valid JWT token
- Active internet connection

---

## Dashboard Layout

### Left Sidebar
- **Logo/Brand**: PoSiFine
- **Navigation Menu**:
  - 📊 Dashboard (overview)
  - 👥 Subscribers (management)
  - 📈 Analytics (detailed reports)
- **User Profile**: Shows owner name
- **Logout Button**: Safely log out

### Main Content Area
- **Header**: Dashboard title + welcome message
- **Metrics Cards**: Quick stats (top of page)
- **Tab Content**: Changes based on selected tab

---

## Key Metrics (Dashboard Tab)

### Metric Cards Display

| Card | Shows | Color |
|------|-------|-------|
| Total Subscribers | All active subscriptions | Blue |
| Active Subscribers | Currently active accounts | Green |
| Monthly Revenue | Total KES earned | Yellow |
| Growth Rate | % growth this month | Purple |

### Real-time Updates
- Click refresh button (🔄) to reload data
- Data auto-refreshes on tab switch
- Metrics update every 5 minutes

---

## Subscribers Tab

### Search & Filter

**Search Box**:
- Search by owner name
- Search by email
- Search by business name
- Results update in real-time

**Status Filter**:
- All Status (default)
- Active (paying subscribers)
- Inactive (not using service)
- Suspended (manually suspended)

**Plan Filter**:
- All Plans (default)
- Basic (KES 1,000/month)
- Ultra (KES 2,500/month)
- Custom (KES 3,500/month)

### Subscriber Table

**Columns**:
1. **Business Name**: Name of the business
2. **Owner**: Owner/admin name
3. **Plan**: Subscription level
4. **Status**: Current status badge
5. **Join Date**: When they subscribed
6. **Actions**: Quick action buttons

### Action Buttons

#### 🔒 Lock/Unlock
- **Green Lock** (🔓): Account is active → Click to suspend
- **Yellow Lock** (🔒): Account is suspended → Click to activate

#### 🗑️ Delete
- Permanently removes subscriber
- Requires confirmation
- Cannot be undone

### Bulk Operations

**Export CSV**:
- Click "Export CSV" button (top right)
- Downloads file: `subscribers-YYYY-MM-DD.csv`
- Contains: Business, Owner, Email, Plan, Status, Join Date
- Opens in Excel/Google Sheets

---

## Analytics Tab

### Time Range Selection

**Available Periods**:
- Last 7 Days (weekly view)
- Last 30 Days (monthly view) - default
- Last 90 Days (quarterly view)
- Last Year (annual view)

### Charts & Visualizations

#### 1. Revenue Trend (Line Chart)
- Shows revenue over time
- Y-axis: Revenue in KES
- X-axis: Time periods (weeks)
- Helps identify growth patterns

#### 2. Plan Distribution (Pie Chart)
- Shows subscriber breakdown by plan
- Basic: ~40%
- Ultra: ~35%
- Custom: ~25%
- Hover to see exact percentages

#### 3. Subscriptions Growth (Bar Chart)
- Shows new subscriptions per period
- Y-axis: Number of new subscriptions
- X-axis: Time periods
- Identifies growth momentum

#### 4. Revenue Breakdown (Stats Cards)
- Revenue by plan (Basic, Ultra, Custom)
- Shows KES amount
- Shows % of total revenue
- Identifies most profitable plan

### KPI Cards (Detailed View)

| KPI | Meaning |
|-----|---------|
| Avg Revenue Per User | Average monthly revenue per subscriber |
| Churn Rate | % of subscribers who cancel monthly |
| LTV (12 months) | Customer lifetime value over 12 months |

### Export Report

**Click "Export Report"**:
- Downloads JSON file with all analytics
- Filename: `analytics-report-YYYY-MM-DD.json`
- Includes metrics, charts data, time range
- Use for further analysis or reporting

---

## Common Tasks

### Finding a Specific Subscriber

1. Go to **Subscribers** tab
2. Type name/email in search box
3. Results filter in real-time
4. Click business name to see more details (future feature)

### Suspending a Problem Subscriber

1. Go to **Subscribers** tab
2. Find subscriber in table
3. Click yellow 🔒 button in Actions column
4. Confirm suspension
5. Status changes to "Suspended"
6. Subscriber can't login or access services

### Reactivating a Suspended Subscriber

1. Filter status to "Suspended"
2. Find subscriber in table
3. Click green 🔓 button
4. Confirm reactivation
5. Status changes to "Active"
6. Subscriber can login again

### Getting Growth Report

1. Go to **Analytics** tab
2. Select time range (Last 30 Days for monthly)
3. View Revenue Trend chart
4. Click "Export Report"
5. Share JSON file with stakeholders

### Comparing Plans

1. Go to **Analytics** tab
2. Look at Plan Distribution pie chart
3. Check Revenue Breakdown cards
4. Identify which plan generates most revenue
5. Use for pricing strategy

---

## Performance Tips

### For Fast Loading
- Use filters to reduce data shown
- Don't export huge datasets
- Refresh data in non-peak hours
- Use Chrome/Firefox (best performance)

### For Accurate Data
- Refresh before important decisions
- Cross-reference with CSV exports
- Check timestamps on metrics
- Look at trends, not single data points

---

## Security & Privacy

### Your Role
- Owner/Main Admin
- Can view all subscriber data
- Can suspend/activate/delete accounts
- Cannot modify payment information

### Subscriber Privacy
- Data is encrypted in transit (HTTPS)
- Data is encrypted at rest (database)
- Only owner can access main admin
- Activities are logged for audit trail

### Best Practices
- Don't share your login
- Log out when done (use Logout button)
- Don't leave browser unattended
- Use strong password (changed regularly)

---

## Frequently Asked Questions

**Q: How often does data refresh?**
A: Data refreshes when you click Refresh button or switch tabs. Auto-refresh every 5 minutes.

**Q: Can I undo a subscriber deletion?**
A: No, deletion is permanent. Be careful with this action.

**Q: Why are some subscribers showing as "Inactive"?**
A: Inactive means they haven't logged in for 30+ days. Still paying though.

**Q: Can I change plan pricing?**
A: Not from Main Admin. Contact development team for pricing changes.

**Q: How do I add a new subscriber?**
A: New subscribers sign up through /plans page. Main Admin can't create accounts manually.

**Q: Can I see subscriber usage?**
A: Not yet. This is coming in future version.

**Q: How do I reset a subscriber's password?**
A: Contact support team. Password reset not available in Main Admin yet.

---

## Support & Issues

**Common Issues**:

| Problem | Solution |
|---------|----------|
| Can't login to Main Admin | Verify owner credentials, check internet |
| Data not updating | Click Refresh, clear browser cache |
| Charts not loading | Check browser console, verify internet |
| Export not working | Disable browser extensions, try different browser |

**Getting Help**:
1. Check this guide first
2. Review error messages in browser console
3. Contact technical support with screenshot

---

## Upcoming Features

- 📍 Subscriber activity logs
- 📧 Send bulk emails to subscribers
- 💳 View payment history
- 🎯 Custom date ranges
- 📱 Mobile app for Main Admin
- 📊 Advanced cohort analysis
- 🔔 Real-time notifications

---

## Quick Stats

**What You Can Do**:
- ✅ View all subscribers
- ✅ Search and filter
- ✅ Suspend/activate accounts
- ✅ Delete accounts
- ✅ Export to CSV
- ✅ View revenue analytics
- ✅ Generate reports
- ✅ Track growth

**What You Cannot Do** (yet):
- ❌ Modify subscriber data
- ❌ Create accounts manually
- ❌ View subscriber logs
- ❌ Send emails
- ❌ Process refunds
- ❌ Change plan pricing

---

**Last Updated**: 2024
**Version**: 1.0
**Status**: Production Ready

