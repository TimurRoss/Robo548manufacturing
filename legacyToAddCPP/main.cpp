#include <bits/stdc++.h>

using namespace std;

int main() {
  ios::sync_with_stdio(0);
  cin.tie(0);
  cout.tie(0);

  int n;
  cin >> n:

  int a[n];
  for (int i = 0; i < n; ++i) cin >> a[i];

  int prev[n + 1];
  prev[0] = 0;
  for (int i = 0; i < n; ++i) prev[i + 1] = prev[i] + a[i];

  for (int i = 0; i <= n; ++i) cout << prev[i];

  return 0;
}
